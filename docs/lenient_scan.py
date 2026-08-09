# -*- coding: utf-8 -*-
"""只读实测：parse_folder_name_lenient 对 H:/Comics/日漫 真实库的批量解析（不改任何代码）"""
import os, re, sys, json
sys.path.insert(0, 'F:/MyProject/008_ComicInfoCover')
from parsers.folder_parser_lenient import parse_folder_name_lenient

ROOT = 'H:/Comics/日漫'
SKIP_DIRS = {'.yacreaderlibrary', '.git', '__pycache__'}
AUTHOR_ONLY = re.compile(r'^\[[^\[\]]+\]$')   # 纯 [作者] 目录
LETTER_BINS = {'A-C','D-G','H-J','K-R','S-T','U-Z'}

def classify(rel_parts, name):
    """返回 (kind, category) — kind: author_dir / work_dir / sub_dir / other"""
    if len(rel_parts) < 2:      # 大类本身或更浅
        return 'other', None
    category = rel_parts[0]
    # 字母分区本身
    if len(rel_parts) == 2 and name in LETTER_BINS:
        return 'other', category
    if AUTHOR_ONLY.match(name):
        return 'author_dir', category
    # 大师作品集: [作者] 目录层
    if category == '大师作品集' and len(rel_parts) == 3:
        return 'author_dir', category
    return 'work_dir', category

rows = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
    rel = os.path.relpath(dirpath, ROOT)
    if rel == '.':
        continue
    rel_parts = rel.split(os.sep)
    name = os.path.basename(dirpath)
    kind, category = classify(rel_parts, name)
    if kind == 'other':
        continue
    try:
        res = parse_folder_name_lenient(name)
    except Exception as e:
        res = {'__error__': repr(e)}
    rows.append({'path': rel, 'name': name, 'kind': kind, 'category': category, 'res': res})

# ---------- 统计 ----------
def is_work(r):
    return r['kind'] == 'work_dir'

def has_error(r):
    res = r['res']
    if res is None or '__error__' in (res or {}):
        return True
    return False

works = [r for r in rows if is_work(r)]
authors = [r for r in rows if r['kind'] == 'author_dir']
subs = [r for r in rows if r['kind'] == 'sub_dir']

err_work = [r for r in works if has_error(r)]
ok_work = [r for r in works if not has_error(r)]

# 异常判定（作品目录）
def anomaly(r):
    res = r['res']
    name = r['name']
    probs = []
    if res is None:
        return ['parser返回None']
    if '__error__' in res:
        return [res['__error__']]
    if not res.get('author'):
        probs.append('author为空(目录名无[作者]或解析失败)')
    if not res.get('series'):
        probs.append('series为空')
    # 目录名含 V\d+ / (V..全) 但卷号没提取
    if re.search(r'[Vv]\d+', name) and res.get('total_volumes', 0) == 0:
        probs.append('目录名含卷号但total_volumes=0')
    if re.search(r'[Vv]\d+', name) and not res.get('vol_info'):
        probs.append('目录名含卷号但vol_info=None')
    # 目录名含"全"但 complete=False（且非短篇/未完结类）
    if re.search(r'全|完结|完\b', name) and not res.get('complete'):
        if res.get('vol_type') != '短篇':
            probs.append('目录名含完结字样但complete=False')
    # series 含可疑残留（括号/卷标）
    if res.get('series') and re.search(r'[\(（\[\[【]|[Vv]\d', res['series']):
        probs.append('series疑似含残留:' + res['series'])
    if res.get('author') and re.search(r'[\(（\[\[【]|[Vv]\d', res['author']):
        probs.append('author疑似含残留:' + res['author'])
    return probs

anoms = [(r, anomaly(r)) for r in works]
anoms = [(r, p) for r, p in anoms if p]

# ---------- 输出 ----------
out = []
out.append('=' * 70)
out.append('H:/Comics/日漫 全库扫描统计')
out.append('=' * 70)
out.append(f'扫描到的目录总数(作品+作者+子目录): {len(rows)}')
out.append(f'  作品目录: {len(works)}  作者目录: {len(authors)}  深层子目录: {len(subs)}')
out.append('')
out.append('-- 按大类分布(作品目录) --')
for cat in ['大师作品集', '完结', '未完结']:
    cw = [r for r in works if r['category'] == cat]
    ce = [r for r in err_work if r['category'] == cat]
    ca = [r for r, _ in anoms if r['category'] == cat]
    out.append(f'  {cat}: 作品{len(cw)}  解析异常(抛错){len(ce)}  可疑案例{len(ca)}')
out.append('')
out.append(f'-- 总成功率 --')
out.append(f'  作品目录总数: {len(works)}')
out.append(f'  正常解析: {len(ok_work)}  ({len(ok_work)/max(len(works),1)*100:.1f}%)')
out.append(f'  解析异常(None/抛错): {len(err_work)}')
out.append(f'  可疑案例(字段缺失/残留等): {len(anoms)}')
out.append('')
out.append('=' * 70)
out.append('异常案例清单（每条: 大类 | 路径 | 问题）')
out.append('=' * 70)
for r, probs in sorted(anoms, key=lambda x: (x[0]['category'], x[0]['path'])):
    out.append(f"[{r['category']}] {r['path']}")
    out.append(f"    目录名: {r['name']}")
    out.append(f"    解析结果: {json.dumps(r['res'], ensure_ascii=False)}")
    out.append(f"    问题: {'; '.join(probs)}")
out.append('')
out.append('=' * 70)
out.append('解析异常(None/抛错) 明细')
out.append('=' * 70)
for r in err_work:
    out.append(f"[{r['category']}] {r['path']}  ->  {r['res']}")

report = '\n'.join(out)
with open('H:/obsidian-vault/ComicInfoScratcher/lenient_report.txt', 'w', encoding='utf-8') as f:
    f.write(report)
print(report[:6000])
print(f'\n... 完整报告已写入 lenient_report.txt ({len(report)} chars, {len(anoms)} anomalies)')
