# ComicInfo 元数据生成器

一个自动从Bangumi API获取漫画信息并生成ComicInfo.xml的工具。支持批量处理漫画文件夹，为CBZ/ZIP格式的漫画文件添加标准的元数据信息。

## 功能特性

- 📚 **自动解析漫画文件夹结构** - 智能识别作者、系列名、卷数等信息
- 🔍 **Bangumi API集成** - 从Bangumi获取漫画元数据和详细信息
- 📝 **生成标准ComicInfo.xml** - 符合ComicInfo.xml标准的元数据文件
- 🎯 **智能匹配** - 支持多作者匹配（如：池上辽一×小池一夫）、别名搜索
- ⚡ **多种处理模式** - 全匹配、高速模式、修正模式、单系列模式
- 🤖 **无人值守模式** - 批量自动处理，无需人工干预
- 🖥️ **图形界面** - 提供PyQt6 GUI界面，操作更直观
- 📦 **ZIP文件操作** - 直接将XML文件写入CBZ/ZIP文件中

## 安装依赖

```bash
pip install requests PyQt6 thefuzz zhconv
```

## 使用方法

### 命令行模式

1. 修改 `config.py` 中的配置（主要是BANGUMI_ACCESS_TOKEN）
2. 运行主程序：
```bash
python main.py
```

### 图形界面模式

```bash
python gui_app.py
```

## 配置说明

在 `config.py` 中设置：

- `BANGUMI_ACCESS_TOKEN`: Bangumi API访问令牌（用于NSFW内容）
- `MODE_SKIP_XMLEXIST`: 处理模式
  - `0` - 全匹配模式（按现有全匹配策略修改ZIP文件）
  - `1` - 高速模式（跳过已有XML的文件）
  - `2` - 修正模式（只处理已有XML的文件）
  - `3` - 指定模式（指定Bangumi ID处理单个系列文件夹）
- `AUTO_TURBO_MATCH`: 无人值守速通模式
  - `0` - 关闭（需要手动选择匹配结果）
  - `1` - 开启（唯一匹配自动处理，其他情况跳过）

## 无人值守模式

启用无人值守模式后，程序将自动处理所有情况，无需人工干预：

- ✅ **唯一匹配结果**：自动处理，生成XML并写入ZIP文件
- ⏭️ **无搜索结果**：直接跳过，不弹出选择菜单
- ⏭️ **作者匹配失败**：直接跳过，不弹出选择菜单
- ⏭️ **无匹配结果**：直接跳过，不弹出选择菜单
- ⏭️ **多个匹配结果**：直接跳过，不弹出选择菜单

设置方法：
```python
AUTO_TURBO_MATCH = 1  # 开启无人值守速通模式
```

## 项目结构

```
ComicInfoScratcher/
├── main.py                   # 主程序入口
├── gui_app.py                # GUI应用入口
├── config.py                 # 配置和常量
├── models/
│   └── bangumi_fetcher.py    # Bangumi API封装
├── parsers/
│   ├── folder_parser.py      # 文件夹名解析
│   └── file_parser.py        # 文件名解析
├── processors/
│   ├── batch_processor.py    # 批量处理器
│   ├── xml_generator.py      # XML生成器
│   └── zip_handler.py        # ZIP文件处理器
├── gui/
│   └── main_window.py        # 主窗口界面
└── utils/
    ├── matcher.py            # 作者匹配工具
    └── path_helper.py        # 路径处理工具
```

## 漫画文件夹命名规范

程序支持以下文件夹命名格式：
- `[作者] 漫画名 (V05全)`
- `[作者] 漫画名 (短篇全)`
- `[作者] 漫画名 (V03全+设定集+番外)`
- `[作者] 漫画名 第1部 (V03 C13)`

## 技术特点

- **模糊匹配**：使用thefuzz库进行智能模糊匹配
- **繁简转换**：使用zhconv库处理繁简体中文转换
- **多作者支持**：支持×、&、/等多种分隔符的多作者匹配
- **智能卷数识别**：自动识别V03、第3卷、Vol.3等多种卷数格式
- **容错处理**：完善的异常处理和超时重试机制

## 系统要求

- Python 3.7+
- 依赖库：requests, PyQt6, thefuzz, zhconv

## 注意事项

- 需要有效的Bangumi API访问令牌来获取NSFW内容
- 建议先在少量漫画上测试，确认效果后再批量处理
- 处理大量文件时建议使用无人值守模式提高效率