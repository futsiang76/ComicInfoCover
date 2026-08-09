# -*- coding: utf-8 -*-
"""只读实测 v2：parse_folder_name_lenient 对 H:/Comics/日漫 真实库批量解析（修正分类+误报）"""
import os, re, sys, json
sys.path.insert(0, 'F:/MyProject/008_ComicInfoCover')
from parsers.folder_parser_lenient import parse_folder_name_lenient

ROOT = 'H:/Comics/日漫'
SKIP_DIRS = {'.yacreaderlibrary', '.git', '__pycache__'}
AUTHOR_ONLY = re.compile(r'^\[[^\[\]]+\]$')   # 纯 [作者]
LETTER_BINS = {'A-C','D-G','H-J','K-R','S-T','U-Z'}
VOL_SUBDIR = re.compile(r'^(?:Vol(?:ume)?\.?\s*|第?\s*)\d+(?:-\d+)?(?:卷|巻|册)?$', re.I)  # "Vol 04" 等卷子目录

def classify(rel_parts, name):
    if len(rel_parts) < 2:
        return 'other', None
    category = rel_parts[0]
    if len(rel_parts) == 2 and name in LETTER_BINS:
        return 'other', category
    if AUTHOR_ONLY.match(name):
        return 'author_dir', category
    if category == '大师作品集' and len(rel_parts) == 3:
        return 'author_dir', category
    if VOL_SUBDIR.match(name) and len(rel_parts) >= 4:
        return 'sub_dir', category
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

works = [r for r in rows if r['kind'] == 'work_dir']
err_work = [r for r in works if r['res'] is None or '__error__' in (r['res'] or {})]
ok_work = [r for r in works if r not in err_work]

def anomaly(r):
    res = r['res']; name = r['name']; probs = []
    if res is None: return ['parser返回None']
    if '__error__' in res: return [res['__error__']]
    if not res.get('author'): probs.append('author为空')
    if not res.get('series'): probs.append('series为空')
    # 卷号：目录名含 (V..全)/V.. 但没提取
    if re.search(r'(?<![A-Za-z])[Vv]\d+', name) and res.get('total_volumes', 0) == 0:
        probs.append('目录名含卷号但total_volumes=0')
    # series 残留：括号/卷标（排除 LV 这类词内 V）
    if res.get('series') and re.search(r'[\(（\[\[]|[Vv]\d+', res['series']):
        probs.append('series疑似含残留:' + res['series'])
    if res.get('author') and re.search(r'[\(（\[\[]|[Vv]\d+', res['author']):
        probs.append('author疑似含残留:' + res['author'])
    return probs

anoms = [(r, anomaly(r)) for r in works if anomaly(r)]

# ---- 跨库一致性（重点维度）----
def cat_works(cat): return [r for r in works if r['category'] == cat]
def cstat(cat, pred): 
    cw = cat_works(cat)
    return sum(1 for r in cw if pred(r)), len(cw)

def vol_mismatch(r):
    """目录名含 (V..全) 但 total_volumes 与数字不符"""
    m = re.search(r'[Vv]\s*(\d+)', r['name'])
    if not m: return False
    return r['res'].get('total_volumes') != int(m.group(1))

out = []
out.append('=' * 72)
out.append('H:/Comics/日漫 全库解析实测（parse_folder_name_lenient）v2')
out.append('=' * 72)
total_all = len(rows)
out.append(f'扫描目录总数: {total_all}  = 作品{len(works)} + 作者目录{sum(1 for r in rows if r["kind"]=="author_dir")} + 卷子目录{sum(1 for r in rows if r["kind"]=="sub_dir")}')
out.append('')
out.append('-- 按大类（作品目录）--')
for cat in ['大师作品集', '完结', '未完结']:
    cw = cat_works(cat)
    ce = [r for r in cw if r['res'] is None or '__error__' in (r['res'] or {})]
    ca = [r for r, _ in anoms if r['category'] == cat]
    comp = sum(1 for r in cw if r['res'] and r['res'].get('complete'))
    nvol = sum(1 for r in cw if r['res'] and r['res'].get('total_volumes', 0) > 0)
    vol_bad = sum(1 for r in cw if vol_mismatch(r))
    out.append(f'  {cat}: 作品{len(cw)}  抛错{len(ce)}  可疑{len(ca)}  complete=True {comp}  有卷号 {nvol}  卷号与目录名不符 {vol_bad}')
out.append('')
out.append('-- 跨库一致性检查 --')
# 完结库应绝大多数 complete=True
cwj = cat_works('完结')
not_comp_fin = [r for r in cwj if r['res'] and not r['res'].get('complete') and r['res'].get('vol_type') != '短篇' and r['res'].get('vol_info')]
out.append(f'  [完结库] 有卷号但 complete=False 的作品: {len(not_comp_fin)}/{len(cwj)}')
for r in not_comp_fin[:15]:
    out.append(f'      {r["name"]}  ->  complete={r["res"]["complete"]} vol_type={r["res"]["vol_type"]} vol_info={r["res"]["vol_info"]}')
cww = cat_works('未完结')
comp_ongoing = [r for r in cww if r['res'] and r['res'].get('complete')]
out.append(f'  [未完结库] complete=True 的作品: {len(comp_ongoing)}/{len(cww)}')
for r in comp_ongoing[:10]:
    out.append(f'      {r["name"]}  ->  vol_info={r["res"]["vol_info"]} tags={r["res"]["tags"]}')
# 大师库
cwd = cat_works('大师作品集')
d_comp = sum(1 for r in cwd if r['res'] and r['res'].get('complete'))
out.append(f'  [大师作品集] complete=True: {d_comp}/{len(cwd)}')
out.append('')
out.append('-- 卷号提取正确性抽查（完结库前20个 (V..全) 案例）--')
cnt = 0
for r in cwj:
    m = re.search(r'[Vv]\s*(\d+)', r['name'])
    if m and cnt < 20:
        ok = 'OK' if r['res'].get('total_volumes') == int(m.group(1)) else f'MISMATCH(name卷={m.group(1)}, parsed={r["res"].get("total_volumes")})'
        out.append(f'  {ok}  {r["name"]} -> total={r["res"].get("total_volumes")} complete={r["res"].get("complete")} vol_type={r["res"].get("vol_type")}')
        cnt += 1
out.append('')
out.append('-- 别名/tag 提取抽查（含 [别名] 或 (tag) 的案例，每类5个）--')
shown = {}
for r in works:
    res = r['res']
    if res is None: continue
    if (res.get('aliases') or res.get('tags')) and r['category'] not in shown:
        out.append(f'  [{r["category"]}] {r["name"]}')
        out.append(f'      aliases={res.get("aliases")} tags={res.get("tags")} extras={res.get("extras")}')
        shown[r['category']] = shown.get(r['category'], 0) + 1
        if shown[r['category']] >= 5: continue
out.append('')
out.append('=' * 72)
out.append('异常/可疑案例清单')
out.append('=' * 72)
for r, probs in sorted(anoms, key=lambda x: (x[0]['category'], x[0]['path'])):
    out.append(f"[{r['category']}] {r['path']}")
    out.append(f"    目录名: {r['name']}")
    out.append(f"    解析: {json.dumps(r['res'], ensure_ascii=False)}")
    out.append(f"    问题: {'; '.join(probs)}")
out.append('')
out.append('-- 卷号与目录名不符（vol_mismatch）全部清单 --')
mm = [r for r in works if vol_mismatch(r)]
out.append(f'共 {len(mm)} 个:')
for r in mm[:40]:
    m = re.search(r'[Vv]\s*(\d+)', r['name'])
    out.append(f'  [{r["category"]}] {r["name"]}  -> parsed total={r["res"].get("total_volumes")} (name卷={m.group(1) if m else "?"})')

report = '\n'.join(out)
with open('H:/obsidian-vault/ComicInfoScratcher/lenient_report_v2.txt', 'w', encoding='utf-8') as f:
    f.write(report)
print(report)
