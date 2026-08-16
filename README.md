# 巴赫康塔塔歌词翻译 · Bach Cantata Chinese Translator

> 一个把巴赫康塔塔（Bach Cantatas）德文歌词自动翻译为**简体中文**的完整管线——抓取德语原文、校验路德圣经经文、填充中文和合本（CUV）经文，最终生成德中逐行对照的 Word 文档（docx）。
>
> A complete pipeline that automatically translates the German libretti of J. S. Bach's cantatas into **Simplified Chinese** — fetching the original German text, cross-referencing Luther's Bible, filling in Chinese Union Version (CUV) scripture, and producing a line-by-line German–Chinese Word document (docx).

> ⚠️ **版本说明**：本项目当前仅提供**简体中文（简中）翻译版本**，暂不含繁体中文版本。若未来需要繁体，可在此译本基础上另行转换。
>
> **Note**: This project currently provides a **Simplified Chinese** translation only. A Traditional Chinese version is not yet available.

---

## 项目简介

巴赫创作了约 200 首留存下来的康塔塔，其歌词（libretti）多为德语巴洛克诗歌，大量化用《圣经》经文与路德宗神学意象，普通读者难以直接读懂。本项目将这一翻译流程**自动化**：

1. **抓取德语原文** —— 从权威站点（UAlberta 等）抓取完整德语歌词与学术脚注；
2. **圣经验证** —— 检索每部康塔塔对应的经课（Epistle/Gospel）与化用的《诗篇》经文；
3. **填充和合本** —— 用中文和合本（CUV）经文作为最高参照；
4. **AI 辅助翻译** —— 以「德语原文 + 和合本经文」为依据逐行翻译（不使用英文译文作参考）；
5. **生成对照文档** —— 输出德中逐行对照的 docx，含脚注超链接与对话角色标签。

## Introduction (English)

J. S. Bach composed roughly 200 surviving cantatas, whose German libretti are steeped in Baroque poetry and dense with biblical allusions and Lutheran theology. This project automates the translation of these texts into Simplified Chinese:

1. **Fetch the German original** — retrieve the full German text and scholarly footnotes from authoritative sources;
2. **Verify against Scripture** — locate the Epistle/Gospel readings and Psalm references underlying each cantata;
3. **Fill in the Chinese Union Version (CUV)** — use the CUV as the highest authority;
4. **AI-assisted translation** — translate line by line based on the German original + CUV scripture (the English translation is *not* used as a reference);
5. **Generate the bilingual document** — output a German–Chinese line-by-line Word document with footnote hyperlinks and dialogue role labels.

---

## 功能特性

- **完整自动化管线**（Step 0 ~ 4.5）：抓取 → 背景 → 术语 → 经文 → 众赞歌 → 翻译 → 成文，一键运行。
- **多数据源与优先级**：UAlberta 为德语歌词主源，kantate.info（NBA 精校文本）为回退源，bachcantatatexts.org 仅作脚注/注释参考。
- **众赞歌翻译子系统**：独立的众赞歌（Chorale）检测、复用、归档、镜像，可与康塔塔管线联动。
- **共享术语库**：宗教术语统一管理于 Excel（`巴赫康塔塔术语库.xlsx`），译文自动同步、译法差异自动标注。
- **圣经经文搜索**：按 BWV 检索 Epistle/Gospel/readings，并对众赞歌做「写作来源 → 经文」模糊匹配，统一填充和合本经文。
- **德中逐行对照 docx**：含基本信息表、脚注超链接、对话角色标签（如「魂 / 耶稣」），字体规范（Times New Roman + 宋体）。

## 效果展示

仓库内已附最新译文示例（对应 `latest translations/`）：

| 作品 | 德中对照 docx | 纯中文 txt |
|------|--------------|-----------|
| BWV 1《Wie schön leuchtet der Morgenstern》 | [`BWV1_德中对照译文.docx`](latest%20translations/BWV_1/BWV1_德中对照译文.docx) | [`BWV1_中文译文.txt`](latest%20translations/BWV_1/BWV1_中文译文.txt) |
| BWV 2《Ach Gott, vom Himmel sieh darein》 | [`BWV2_德中对照译文.docx`](latest%20translations/BWV_2/BWV2_德中对照译文.docx) | [`BWV2_中文译文.txt`](latest%20translations/BWV_2/BWV2_中文译文.txt) |
| BWV 194《Höchsterwünschtes Freudenfest》 | [`BWV194_德中对照译文.docx`](latest%20translations/BWV_194/BWV194_德中对照译文.docx) | [`BWV194_中文译文.txt`](latest%20translations/BWV_194/BWV194_中文译文.txt) |

众赞歌示例：[`Chorale026_德中对照译文.docx`](巴赫康塔塔中的众赞歌/latest%20translation/Chorale026_德中对照译文.docx)

## 项目结构

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
├── latest translations/             # 最新译文镜像（BWV 1 / 2 / 194）
├── 巴赫康塔塔术语库.xlsx              # 共享术语库
└── bach_vocal_index.json            # IMSLP 巴赫声乐作品索引
```

## 环境要求

- **Python 3.9+**（开发环境为 3.13）
- **UTF-8 环境**：项目目录与 Python 包名含中文（如 `巴赫康塔塔中的众赞歌`），需在 UTF-8 环境下运行；Windows 默认支持，Linux/macOS 亦默认 UTF-8。
- 首次运行需要联网（抓取歌词与经文）。

## 安装

```bash
# 1. 克隆仓库
git clone https://github.com/2129084619-cmd/bach-cantata-Chinese-translator.git
cd bach-cantata-Chinese-translator

# 2. 安装依赖（建议使用虚拟环境）
pip install -r requirements.txt
```

### （可选）安装为 WorkBuddy skill

本项目同时提供一份 `SKILL.md`，可作为 WorkBuddy（CodeBuddy）的 skill 使用：

1. 将 `SKILL.md` 复制到 `~/.workbuddy/skills/bach-cantata-translate/SKILL.md`；
2. 若你使用 WorkBuddy 托管 Python，请把 `SKILL.md` 中的 `python` 命令替换为你的实际解释器路径（如 `C:\Users\<你>\.workbuddy\binaries\python\envs\default\Scripts\python.exe`）；
3. 之后即可在对话中调用 `/巴赫康塔塔歌词翻译 <BWV>`。

## 快速开始

```bash
# 翻译 BWV 1《Wie schön leuchtet der Morgenstern》
python -m pipeline.main 1

# 强制重新抓取
python -m pipeline.main 1 --force

# 查询 BWV 对应的众赞歌
python -m 巴赫康塔塔中的众赞歌.chorale_main 1

# 重建 / 查看众赞歌索引
python -m 巴赫康塔塔中的众赞歌.chorale_main --rebuild-index
python -m 巴赫康塔塔中的众赞歌.chorale_main --status
```

> 说明：命令行管线负责「抓取 + 背景 + 经文 + 众赞歌检测」，并生成含 `【待翻译】` 占位符的 docx 模板与翻译上下文（JSON）；**最终的中文逐行翻译由 AI 助手完成**（见下方「翻译标准」），完成后写回 docx 并镜像到 `latest translations/`。

## 翻译管线说明

| 步骤 | 名称 | 职责 |
|------|------|------|
| Step A0 | IMSLP 预检 | 校验 BWV 是否为巴赫声乐作品 |
| Step A | 运行 Python 管线 | 抓取德语原文、脚注、背景、术语、经文、众赞歌 |
| Step B | 填充和合本经文 | 用 WebFetch 从 BibleGateway 取 CUV 中文经文 |
| Step C | 重建翻译上下文 | 汇总 texts/footnotes/glossary/bible/metadata |
| Step D | AI 中文翻译 | 以德语原文 + 和合本为最高依据逐乐章翻译 |
| Step E | 生成德中 docx | 替换占位符，设置字体规范 |
| Step E2 | 注入脚注超链接 | 为脚注上标追加超链接 |
| Step E3 | 导出 TXT + 镜像 | 写纯中文 txt，镜像到 `latest translations/` |
| Step F | 展示结果 | 展示最终 docx 与 txt |

## 翻译标准

1. **语义准确性优先**：以德语原文 + 中文和合本（CUV）为最高依据，**不使用英文译文作翻译参考**（bachcantatatexts.org 英文仅作注释素材）。
2. **行数强制一致**：每个乐章/诗节的德语行数 = 中文行数，不可合并或拆分导致总数偏差。
3. **行内句意不可碎片化**：每行承载独立完整的意群，跨行意译允许，但每行应有可辨识的语义。
4. **相邻行不可重复**：前后行不承载相同/近似的句意。
5. **成对词语不可拆分**：`Eia, eia`、`Amen! Amen!`、`Singet, springet` 等必须合为一行。
6. **术语统一**：宗教专有名词严格对齐共享术语库与和合本译法。
7. **背景标注**：超出和合本范围的神学/文化背景以方括号 `[注：...]` 标注。

## 数据来源与版权声明

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

## 已知限制

- 部分站点抓取时需关闭 SSL 校验（`verify=False`），仅为规避证书问题，非安全风险。
- 中文和合本经文需通过 WebFetch（JS 渲染页面）手动填充，未完全自动化。
- 最终翻译由 AI 助手完成（以和合本为最高参照），可能存在偏差，建议人工校对。
- 部分众赞歌详情页 HTML 结构特殊，诗歌文本提取可能不完整。
- 跨平台使用中文包名（`巴赫康塔塔中的众赞歌`）时需确保 UTF-8 环境。

## License

本项目采用 [MIT License](LICENSE)，版权 © 2026 2129084619-cmd。

> 再次提醒：仓库内附带的歌词、译文、脚注与经文内容版权归各自原作者所有，与本项目的 MIT 协议无关。
