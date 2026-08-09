# -*- coding: utf-8 -*-
"""宽松解析规则原型测试 — 验证新规则能覆盖多少格式（不改生产代码）

规则（用户 2026-08-06 定义）：
1. 作者 = 第一个 [..]（必须）
2. 主名 = 作者后、下一个括号前的内容，原样保留（不做中英拆分）
3. 括号（[]/()/其它）内的内容：
   - 命中黑名单 → tag（语言/版本/来源/类型等标记）
   - 含卷标（V/Vol/卷/册/期/C/chapter/volume + 数字，或中文数字）→ 卷信息
   - 其余 → 别名
4. 完结判定：卷括号内出现 全/完结/end/completed → 已完结；未完结/连载中/ongoing → 连载；无 → 默认未完结
"""
import re, sys

# ---- 黑名单（tag 词表，初版）----
TAG_BLACKLIST = {
    # 语言
    "日", "中", "英", "汉", "繁", "简", "双语", "日文", "中文", "英文", "简中", "繁中",
    "日文原版", "日版", "台版", "港版", "大陆版", "国漫", "日漫",
    # 版本
    "完全版", "爱藏版", "电子版", "文库版", "新装版", "纪念版", "收藏版", "典藏版",
    "全彩", "彩色版", "黑白", "扫描版", "修复版", "高清", "HD", "DX",
    # 来源
    "汉化", "生肉", "自购", "扫图", "自扫", "转载", "精排", "修复", "民间汉化",
    # 类型
    "完结", "连载中", "短篇", "单行本", "画集", "原画集", "设定集", "公式书",
    "番外", "外传", "特别篇", "总集篇", "同人", "合集", "精选集", "别册",
    # 其它
    "授权版", "官方", "台版授权",
}

# 展会码 C97/C99/C100 等
TAG_C_EVENT = re.compile(r"^C\d{2,3}$", re.IGNORECASE)

# ---- 卷标正则（宽松）----
# V/Vol/volume/卷/册/期/C/chapter + 数字（含中文数字 一二三.../壹贰叁）
VOL_RE = re.compile(
    r"(?:"
    r"[Vv][Oo][Ll]?\.?\s*[0-9０-９]+|"        # V1 / Vol.1 / vol 1
    r"[Vv][Oo][Ll][Uu][Mm][Ee]\.?\s*[0-9０-９]+|"  # volume 1
    r"卷\s*[0-9０-９一二三四五六七八九十百]+|"     # 卷1 / 卷二十
    r"册\s*[0-9０-９一二三四五六七八九十百]+|"     # 册2
    r"期\s*[0-9０-９一二三四五六七八九十百]+|"     # 期3
    r"[Cc]\s*[0-9０-９]+|"                     # C1 / c1
    r"[Cc][Hh][Aa][Pp][Tt][Ee][Rr]\.?\s*[0-9０-９]+|"  # chapter 1
    r"[0-9０-９]+\s*卷|"                       # 1卷
    r"[0-9０-９]+\s*冊|"                       # 1冊
    r"[0-9０-９]+\s*话|"                       # 1话
    r"[一二三四五六七八九十百]+\s*卷|"           # 二十卷
    r"[一二三四五六七八九十百]+\s*話"           # 十話
    r")"
)

# 完结标记
COMPLETE_WORDS = {"全", "完结", "完", "end", "completed", "fin", "complete"}
ONGOING_WORDS = {"未完结", "连载中", "连载", "ongoing", "未完"}

# ---- 全角转半角 ----
def to_halfwidth(s):
    out = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)

def is_tag_candidate(text):
    """判断是否为 tag 类（黑名单或展会码）"""
    t = text.strip()
    if not t:
        return True
    if t in TAG_BLACKLIST:
        return True
    if TAG_C_EVENT.match(t):
        return True
    return False

def is_volume_content(text):
    """判断括号内容是否含卷标"""
    return bool(VOL_RE.search(to_halfwidth(text)))

def parse_folder_lenient(folder_name):
    """宽松解析器原型（新规则）"""
    name = folder_name.strip()
    
    # 1. 作者 = 第一个 [..]
    m = re.match(r"^\[([^\]]+)\]", name)
    if not m:
        # 无作者格式（容忍）：作者留空
        author = ""
        rest = name
    else:
        author = m.group(1).strip()
        rest = name[m.end():].strip()
    
    # 2. 提取所有括号（[]/()/全角（））
    bracket_pattern = re.compile(r"[\[（(]([^\]）)]+)[\]）)]")
    bracket_contents = []
    positions = []
    for bm in bracket_pattern.finditer(rest):
        bracket_contents.append(bm.group(1).strip())
        positions.append(bm.span())
    
    # 3. 主名 = 第一个括号前的内容（原样保留）
    if positions:
        series_raw = rest[:positions[0][0]].strip()
    else:
        series_raw = rest.strip()
    series_name = series_raw
    
    # 4. 分类括号内容
    aliases = []
    tags = []
    vol_info = None
    complete = False
    vol_type = "连载"
    
    for content in bracket_contents:
        c = content.strip()
        if is_volume_content(c):
            vol_info = c
            # 完结判定
            low = c.lower()
            if any(w in low for w in COMPLETE_WORDS):
                complete = True
                vol_type = "已完结"
            elif any(w in low for w in ONGOING_WORDS):
                complete = False
                vol_type = "连载"
        elif is_tag_candidate(c):
            tags.append(c)
        else:
            aliases.append(c)
    
    # 5. 提取卷数
    total_volumes = 0
    if vol_info:
        half = to_halfwidth(vol_info)
        vm = re.search(r"(\d+)", half)
        if vm:
            total_volumes = int(vm.group(1))
        else:
            # 中文数字
            cn = re.search(r"[一二三四五六七八九十百]+", half)
            if cn:
                cn_map = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}
                total_volumes = 10 if cn.group(0) == "十" else len(cn.group(0))
    
    # 6. 完结标记可能在主名里（如 [完结] 在括号里被当 tag，但卷信息在别处）
    if vol_info is None and any(w in name.lower() for w in COMPLETE_WORDS):
        # 无卷信息但有完结字 → 完结
        pass
    
    return {
        "author": author,
        "series": series_name,
        "aliases": aliases,
        "tags": tags,
        "vol_info": vol_info,
        "total_volumes": total_volumes,
        "vol_type": vol_type,
        "complete": complete,
    }

# ---- 测试样本 ----
if __name__ == "__main__":
    samples = [
    # 用户自用格式
    "[河合孝典] 杀手餐厅 (V04)",
    "[金城宗幸×野村优介] 蓝色监狱 [Blue Lock] (V23)",
    "[黑乃奈奈绘] 和平捍卫队 铁 [新撰组异闻录 铁][Peace Maker II] (V05)",
    "[白土三平] カムイ伝 第二部 [卡姆伊传 第二部] [日] (V22全 缺V21)",
    "[比良贺みん也] 化身者 (短篇)",
    "[士郎正宗] 攻壳机动队 (V02全+原画集)",
    "[田中政志] 小恐龙阿冈GON (V07全+精选集)",
    "[赤人义一] 尸姬 (V23全+尸解教典)",
    "[贺东招二×上田宏] 惊爆危机 Σ [全金属狂潮 Σ] (V19全)",
    # 外部格式
    "[城市风云儿][青山刚昌][Vol.01-Vol.24][完结][日本小学馆授权台湾中文版][C.C扫图]",
    "Name of Manga - c006-010 (v02) [FooScans].zip",
    "エロマンガ先生 第01-12巻 [Ero Manga Sensei vol 01-12]",
    "[ENG] One Piece - Vol. 106 (FULL COLOR Digital Colored Comics)",
    "Spy x Family Vol.16 - Vol.17",
    "【BLVEFO9】喂我吃吧 老師!",
    "JM248965-喂我吃吧 老師!",
    "《作品名》第X话 [汉化组名].zip",
    "漫画名V01",
    "(C97) [社团名 (作者名)] 标题",
    "[聖鬥士星矢][車田正美][Vol.01-Vol.22][完结][天下][完全版][C.C]",
]

    print("=" * 100)
    for s in samples:
        r = parse_folder_lenient(s)
        if r:
            print(f"📁 {s}")
            print(f"   作者={r['author']!r} 主名={r['series']!r}")
            print(f"   别名={r['aliases']} tag={r['tags']}")
            print(f"   卷={r['vol_info']!r} 卷数={r['total_volumes']} 类型={r['vol_type']} 完结={r['complete']}")
        else:
            print(f"📁 {s} → 解析失败")
        print("-" * 100)
