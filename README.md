# 巴赫康塔塔歌词翻译 · Bach Cantata Chinese Translator

> 一套面向本地 AI Agent 的巴赫声乐作品翻译工具链，包含三大能力：**康塔塔歌词翻译**、**众赞歌翻译**、**共享术语库**。抓取德语原文 → 校验路德圣经 → 填充中文和合本（CUV）经文 → AI 逐行翻译 → 生成德中对照 Word 文档。
>
> A toolchain for local AI agents covering three capabilities: **cantata lyric translation**, **chorale translation**, and a **shared glossary**. It fetches the German original, cross-references Luther's Bible, fills in Chinese Union Version (CUV) scripture, performs AI line-by-line translation, and produces a German–Chinese Word document.

> ⚠️ **注意 / Note**：
> 本项目当前仅提供**简体中文（简中）翻译版本**，暂不含繁体中文。This project currently provides a **Simplified Chinese** translation only.
> 本项目由 AI Agent 开发，尚处于不断完善中，可能存在准确性问题；如遇运行问题请在 Discussion 留言。This project is built by an AI agent and is still evolving; accuracy issues may exist — please report problems in the Discussion section.

---

## 功能总览 / Feature Overview

本项目围绕「把巴赫声乐作品译成简体中文」这一目标，提供三个相互联动的功能模块：

| 功能 | 说明 |
|------|------|
| **① 康塔塔歌词翻译** | 一键运行完整管线（Step 0 ~ 4.5），抓取德语歌词与学术脚注、检索对应经课（Epistle/Gospel）与化用经文、填充和合本、AI 逐行翻译、生成含脚注超链接与对话角色标签的德中对照 docx。 |
| **② 众赞歌翻译** | 独立的众赞歌（Chorale）子系统，支持 BWV→众赞歌映射检测、跨康塔塔复用、重译归档（按文件修改时间留档）与 latest 镜像，可与主管线联动。 |
| **③ 共享术语库** | 宗教术语统一管理于 `巴赫康塔塔术语库.xlsx`，自动追加新术语、更新频次、标注同一术语在不同康塔塔的译法差异，确保译法一致。 |

### English

| Feature | Description |
|---------|-------------|
| **① Cantata translation** | One-command pipeline (Step 0–4.5) that fetches German lyrics + scholarly footnotes, locates the Epistle/Gospel and Psalm references, fills in CUV scripture, performs AI translation, and outputs a German–Chinese docx with footnote hyperlinks and dialogue role labels. |
| **② Chorale translation** | A standalone chorale subsystem: BWV→chorale detection, cross-cantata reuse, re-translation archiving (keyed by file modification time) and latest-mirroring, integrated with the main pipeline. |
| **③ Shared glossary** | Religious terminology centralized in `巴赫康塔塔术语库.xlsx`, auto-appending new terms, updating frequency, and flagging translation divergences across cantatas. |

---

## 翻译流程与译文展示 / Pipeline & Samples

### 翻译流程

```
IMSLP 预检 → 抓取德语原文/脚注 → 背景与经课 → 术语表 + 路德验证
   → 中文经文清单 → 众赞歌经文模糊搜索 → 翻译上下文 → AI 逐行翻译
   → 生成德中 docx → 注入脚注超链接 → 导出纯中文 txt + 镜像
```

命令行管线负责「抓取 + 背景 + 经文 + 众赞歌检测」，生成含 `【待翻译】` 占位符的 docx 模板与翻译上下文（JSON）；**最终中文逐行翻译由 AI 助手完成**，完成后写回 docx 并镜像到 `latest translations/`。

### 已上传译文 / Included translations

仓库内附最新译文示例（对应 `latest translations/`）：

| 作品 | 德中对照 docx | 纯中文 txt |
|------|--------------|-----------|
| BWV 1《Wie schön leuchtet der Morgenstern》 | [BWV1 docx](latest%20translations/BWV_1/BWV1_德中对照译文.docx) | [BWV1 txt](latest%20translations/BWV_1/BWV1_中文译文.txt) |
| BWV 2《Ach Gott, vom Himmel sieh darein》 | [BWV2 docx](latest%20translations/BWV_2/BWV2_德中对照译文.docx) | [BWV2 txt](latest%20translations/BWV_2/BWV2_中文译文.txt) |
| BWV 60《O Ewigkeit, du Donnerwort》 | [BWV60 docx](latest%20translations/BWV_60/BWV60_德中对照译文.docx) | [BWV60 txt](latest%20translations/BWV_60/BWV60_中文译文.txt) |
| BWV 194《Höchsterwünschtes Freudenfest》 | [BWV194 docx](latest%20translations/BWV_194/BWV194_德中对照译文.docx) | [BWV194 txt](latest%20translations/BWV_194/BWV194_中文译文.txt) |

众赞歌示例：[Chorale026 docx](巴赫康塔塔中的众赞歌/latest%20translation/Chorale026_德中对照译文.docx)

---

## Skill 部署安装 / Deploy as an Agent Skill

本项目同时是一份 **WorkBuddy / CodeBuddy skill**（`SKILL.md` 操作手册），可部署到本地 AI Agent，用一句自然语言命令即可触发完整翻译流程（如 `/巴赫康塔塔歌词翻译 60`）。

### 1. 环境要求 / Environment

- **Python 3.9+**（开发环境为 3.13）
- **UTF-8 环境**：项目目录与 Python 包名含中文（如 `巴赫康塔塔中的众赞歌`），Windows 默认支持，Linux/macOS 亦默认 UTF-8
- **联网**：首次运行需联网抓取歌词与经文
- **依赖**（见 `requirements.txt`）：`requests`、`python-docx`、`beautifulsoup4`、`openpyxl`、`lxml`、`pdfplumber`

```bash
git clone https://github.com/2129084619-cmd/bach-cantata-Chinese-translator.git
cd bach-cantata-Chinese-translator
pip install -r requirements.txt
```

### 2. 部署到 WorkBuddy / CodeBuddy（原生支持）

1. 克隆本仓库后，将 `SKILL.md` 复制到用户级 skill 目录：
   ```bash
   mkdir -p ~/.workbuddy/skills/bach-cantata-translate
   cp SKILL.md ~/.workbuddy/skills/bach-cantata-translate/SKILL.md
   ```
2. 若你使用 WorkBuddy 托管的 Python，请把 `SKILL.md` 里的 `python` 命令替换为你的实际解释器路径（如 `C:\Users\<你>\.workbuddy\binaries\python\envs\default\Scripts\python.exe`）。
3. 之后即可在对话中输入 `/巴赫康塔塔歌词翻译 <BWV>` 或 `/巴赫康塔塔歌词翻译 chorale <BWV>`。

### 3. 部署到其他 Agent 工具（需适配）

`SKILL.md` 是通用格式的操作手册 + 命令行调用，可适配以下常见 Agent 工具（skill / rules / 自定义指令目录各有不同）：

| 工具 | 部署位置 | 说明 |
|------|---------|------|
| **WorkBuddy / CodeBuddy**（腾讯） | `~/.workbuddy/skills/<name>/SKILL.md` | 原生支持，直接调用 |
| **Claude Code**（Anthropic） | `~/.claude/skills/<name>/SKILL.md` | 支持 skills 机制，把 SKILL.md 放入即可 |
| **Cursor** | `.cursor/rules/` 或项目 skill 目录 | 将 SKILL.md 内容改写为 `.mdc` rule，或直接作为自定义指令引用 |
| **Windsurf**（Codeium） | `.windsurf/rules/` | 同上，改写为 rules 格式 |
| **通义灵码**（阿里） | 自定义指令 / 项目规则 | 把 SKILL.md 关键流程粘贴为自定义指令 |
| **文心快码 / 豆包 MarsCode / Kimi** | 各自的自定义 skill / 规则目录 | 核心是「管线命令 + 翻译标准」，移植成本低 |

> 核心提示：无论部署到哪个工具，本质都是让 Agent 理解两件事——**① 用什么命令跑管线**（`python -m pipeline.main <BWV>`），**② 翻译要遵循什么标准**（见下方「翻译标准」）。`SKILL.md` 已把这两点写成可直接执行的流程，其余工具只需把命令路径换成你的解释器。

---

## 使用方法 / Usage

```bash
# 翻译 BWV 1《Wie schön leuchtet der Morgenstern》
python -m pipeline.main 1

# 强制重新抓取
python -m pipeline.main 1 --force

# 查询 BWV 对应的众赞歌
python -m 巴赫康塔塔中的众赞歌.chorale_main 1

# 手动翻译某 BWV 对应的众赞歌（生成 docx 模板后由 AI 填译）
python -m 巴赫康塔塔中的众赞歌.chorale_main 1 --regenerate

# 重建 / 查看众赞歌索引
python -m 巴赫康塔塔中的众赞歌.chorale_main --rebuild-index
python -m 巴赫康塔塔中的众赞歌.chorale_main --status
```

作为 skill 使用时的对话命令：

```
/巴赫康塔塔歌词翻译 1                 # 翻译 BWV 1（完整管线）
/巴赫康塔塔歌词翻译 chorale 4         # 查询 BWV 4 对应众赞歌
/巴赫康塔塔歌词翻译 chorale 4 --翻译  # 手动翻译 BWV 4 对应众赞歌
/巴赫康塔塔歌词翻译 update           # 更新后端管线代码
```

---

## 项目结构 / Project Structure

```
.
├── README.md                        # 本文件
├── LICENSE                          # MIT 协议
├── requirements.txt                 # Python 依赖
├── SKILL.md                         # WorkBuddy skill 操作手册
├── pipeline/                        # 主管线
│   ├── main.py                      # 主编排器（python -m pipeline.main <BWV>）
│   ├── config.py                    # 路径 / URL 模板 / 书卷名三语映射 / 角色名集合
│   ├── logger.py                    # 日志
│   ├── step0_setup.py               # Step 0：建目录
│   ├── step1_uofa.py                # Step 1（主）：UAlberta 德语歌词
│   ├── step1_kantate.py             # Step 1（备）：kantate.info
│   ├── step1_fetch_texts.py         # Step 1（旧）：bachcantatatexts.org JSON
│   ├── step2_fetch_bg.py            # Step 2：背景元数据 + 经课
│   ├── step25_glossary.py           # Step 2.5：术语表 + 路德经文验证
│   ├── step3_fetch_bible.py         # Step 3：中文经文清单
│   ├── step35_chorale_bible.py      # Step 3.5：众赞歌→经文模糊搜索
│   ├── step4_translate.py           # Step 4：翻译上下文 + 德中 docx
│   ├── step45_chorale_reuse.py      # Step 4.5：众赞歌复用检测
│   ├── glossary_db.py               # 术语库 Excel 读写
│   ├── imslp_index.py               # IMSLP 声乐作品索引
│   └── backfill_chorale_cn.py       # 众赞歌中文回填工具
├── 巴赫康塔塔中的众赞歌/             # 众赞歌翻译子系统
│   ├── chorale_main.py              # CLI 入口
│   ├── chorale_api.py               # 高级 API（翻译管线 / 写回）
│   ├── chorale_translator.py        # 众赞歌 docx 生成器
│   ├── chorale_index.py             # 索引构建器
│   ├── chorale_scraper.py           # 详情页抓取
│   ├── chorale_integration.py       # 与主管线集成
│   ├── chorale_config.py            # 配置
│   ├── chorale_index.json           # BWV→众赞歌映射索引（333 首 / 477 映射）
│   ├── chorale_bible_sources.json   # 众赞歌经文来源缓存
│   └── data/                        # 已抓取的众赞歌详情（ChoraleNNN.json）
├── latest translations/             # 最新译文镜像
├── 巴赫康塔塔术语库.xlsx              # 共享术语库
└── bach_vocal_index.json            # IMSLP 巴赫声乐作品索引
```

---

## 翻译标准 / Translation Standards

1. **语义准确性优先**：以德语原文 + 中文和合本（CUV）为最高依据，**不使用英文译文作翻译参考**（bachcantatatexts.org 英文仅作注释素材）。
2. **行数强制一致**：每个乐章/诗节的德语行数 = 中文行数，不可合并或拆分导致总数偏差。
3. **行内句意不可碎片化**：每行承载独立完整的意群，跨行意译允许，但每行应有可辨识的语义。
4. **相邻行不可重复**：前后行不承载相同/近似的句意。
5. **成对词语不可拆分**：`Eia, eia`、`Amen! Amen!`、`Singet, springet` 等必须合为一行。
6. **术语统一**：宗教专有名词严格对齐共享术语库与和合本译法。
7. **背景标注**：超出和合本范围的神学/文化背景以方括号 `[注：...]` 标注。

---

## 数据来源与版权声明 / Sources & Copyright

本项目抓取并参考了以下公开资源，**其歌词、译文与注释的版权归各自原作者所有**：

| 来源 | 用途 |
|------|------|
| [UAlberta cantatas](https://sites.ualberta.ca/~wfb/cantatas/) | 德语歌词主源 |
| [BachCantataTexts.org](https://bachcantatatexts.org) | 脚注 / 英文译文（仅作注释参考） |
| [Bach-Cantatas.com](https://www.bach-cantatas.com) | 背景资料、经课、众赞歌 |
| [Bachipedia.org](https://www.bachipedia.org) | 德语背景 + 经文引用 |
| [kantate.info](http://www.kantate.info) | NBA 精校文本（回退源） |
| [Hymnary.org](https://hymnary.org) | 众赞歌写作来源 |
| [BibleGateway](https://www.biblegateway.com) / [BiblePortal](https://bibleportal.com) | 路德 1545 与中文和合本经文 |
| [IMSLP](https://imslp.org) | 巴赫声乐作品索引 |

> ⚠️ 本项目**仅供学习与研究用途，请勿用于商业目的**，使用抓取内容时请遵守各源站点的使用条款。

---

## 已知限制 / Known Limitations

- 部分站点抓取时需关闭 SSL 校验（`verify=False`），仅为规避证书问题，非安全风险。
- 中文和合本经文需通过 WebFetch（JS 渲染页面）手动填充，未完全自动化。
- 最终翻译由 AI 助手完成（以和合本为最高参照），可能存在偏差，建议人工校对。
- 在对话康塔塔的翻译中仍可能把角色名误识别为歌词并翻译。
- 部分众赞歌详情页 HTML 结构特殊，诗歌文本提取可能不完整。
- 跨平台使用中文包名（`巴赫康塔塔中的众赞歌`）时需确保 UTF-8 环境。
- bachcantatatexts.org 与 UAlberta 的歌词行分割偶有差异（个别长句合行），导致极少数脚注锚点存在 1 行偏差。

---

## License

本项目采用 [MIT License](LICENSE)，版权 © 2026 2129084619-cmd。

> 再次提醒：仓库内附带的歌词、译文、脚注与经文内容版权归各自原作者所有，与本项目的 MIT 协议无关。
