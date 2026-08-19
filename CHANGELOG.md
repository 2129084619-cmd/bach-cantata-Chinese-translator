# 更新日志 / Changelog

本项目遵循语义化版本（SemVer），版本号采用 `x.y.z` 三段式十进制：`x` 主版本、`y` 次版本（大更递增）、`z` 补丁号（小更递增，0-99）。大更时 `y+1` 且 `z` 清零（如 `1.0.19` → `1.1.0`）；小更时仅 `z+1`。

本文档记录影响用户可见行为的重要变更；纯内部重构、琐碎修复与文档润色未逐一列出。

---

## [1.0.2] - 2026-08-19（补丁小更）

### 🩹 Patch Note（补丁说明）

本次补丁解决三个解析问题，并为**乐章识别**建立跨数据源交叉验证机制。

**问题背景 1 — 众赞歌康塔塔乐章识别**：BWV 4《Christ lag in Todes Banden》实际有 8 个乐章（Sinfonia + 7 个众赞歌诗节），但旧代码的乐章标题识别只认 `Coro`/`Aria`/`Choral`/`Chorus`/`Sinfonia`/`Duetto`/`Arioso` 这些关键词。BWV 4 的部分诗节标题是「3. Versus 2 S A」「4. Versus 3 T」这类**不含上述关键词**的格式，于是整首诗节标题被当成歌词行，8 个乐章被压缩成 3 个——歌词里混着「3. Versus 2 S A」这样的排印残留，脚注也无法正确对齐。

> **BWV 4 乐章结构说明**：8 个乐章中，Mvt 1 为 Sinfonia；Mvt 2（「2. Coro Versus 1 S A T B」）与 Mvt 5（「5. Coro Versus 4 S A T B」）**标有 `Coro`，是明确的合唱（Chorus）乐章**；其余 Mvt 3/4/6/7/8 为「Versus N + 声部」格式（「Versus 2 S A」「Versus 3 T」「Versus 5 B」「Versus 6 S T」「Versus 7 S A T B」），**配器自由度较高，既可 OVPP（每声部一人）也可由合唱团演唱**，故**保留 `Versus` 类型标记**（众赞歌诗节），不强判为合唱、也不强行改写为 `chorale`。
>
> BWV 62、91 等其他众赞歌康塔塔在 UAlberta 上用的是标准乐章关键词（`Coro`/`Aria`/`Choral` 等），**并非** BWV 4 的 `Versus` 格式，本补丁对它们无影响。

**问题背景 2 — 德语书卷名未归一化**：圣经经文清单生成时，直接用了巴赫来源站点的德语书卷名（如「Markus」），未映射回英语标准名（「Mark」），导致经文清单显示「Markus」而非「马可福音」，且 BibleGateway 查询 URL 因书卷名无效而抓取失败。

**问题背景 3 — 纯 `Coro` 的合唱/众赞歌歧义**：UAlberta 用同一个 `Coro` 同时表示**开场大合唱**（Chorus）和**结尾四声部众赞歌**（Chorale）。例如 BWV 100《Was Gott tut, das ist wohlgetan》的 Mvt 1 是开场合唱、Mvt 6 是结尾众赞歌，两者在 UAlberta 都标为「Coro」；BWV 117 的 Mvt 1/Mvt 9 同理。旧代码把一切 `Coro` 一律判为 `Chorus`，导致结尾众赞歌被误判为合唱，进而使众赞歌复用检测（step45）漏掉该乐章、无法回填对应的赞美诗诗节。

**修复内容**（四项改动）：

| 文件 | 改动 |
|------|------|
| `pipeline/step1_uofa.py` | ① 识别条件新增 `'Versus'`，`Versus` 标题**保留 `type='Versus'` 不变**（含 `Coro` 的「Coro Versus」仍优先判为 Chorus）；② 遇到「数字. 标题」但**不含任何已知关键词**时，创建 `type='unknown'` 占位乐章（`is_uncertain_type=True`），不再混入上一乐章歌词；③ 含 `Versus` 的乐章标记 `has_chorale=True`（供众赞歌复用检测）；④ 纯 `Coro`（不带 Versus/Choral/Chorale/Chorus 修饰）标记 `is_ambiguous_chorus=True`，供 Step 1.7 交叉验证 |
| `pipeline/step2_fetch_bg.py` | 乐章提取新增 Strategy 3，识别 bach-cantatas.com 的 `Versus N [voices]` 单行格式（movement number = N+1），使 `movement_info` 对众赞歌康塔塔完整（BWV 4 提取到 8 乐章） |
| `pipeline/step3_fetch_bible.py` | 生成 manifest 前先 `BOOK_GERMAN_REVERSE_MAP.get(raw_book, raw_book)` 归一化书卷名 |
| `pipeline/main.py` | 新增 **Step 1.7**：① 用 bach-cantatas.com 的 `movement_info` 把 `type='unknown'` 的乐章回填为标准类型；② 对 `is_ambiguous_chorus=True` 的「纯 Coro」乐章交叉验证——bach-cantatas.com 标 `Chorale` 则回填 `type='chorale'`（`has_chorale=True`），标 `Chorus` 则保持 Chorus |
| `pipeline/step45_chorale_reuse.py` | 众赞歌复用检测新增 `'versus' in type` 识别，使 `type='Versus'` 的诗节乐章被直接识别（此前仅依赖 `has_chorale` 标志） |

**效果**：BWV 4 正确拆分出 8 个乐章（Mvt 2/5 = Chorus，其余 = Versus），20 条脚注 18 处锚点全部对齐，gospel 经文正确显示「马可福音」并可正常抓取；众赞歌复用检测覆盖全部 7 个诗节。BWV 100 的 Mvt 6、BWV 117 的 Mvt 9（结尾众赞歌）经交叉验证正确回填为 `chorale`，step45 得以识别并回填对应赞美诗诗节；开场合唱（Mvt 1）仍正确保持 `Chorus`。

**回归验证**：BWV 62（6 乐章）、BWV 91（6 乐章）标准关键词格式解析不受影响；BWV 4 的「Coro Versus」乐章不受歧义交叉验证影响（保持 Chorus）；日期行（"3. Dezember 1724" 等）在 UAlberta 的 `Besetzung` 之后，被 `break` 拦截不进入歌词。

**附带**：新增 BWV 4《Christ lag in Todes Banden》完整译文（56 行 / 20 脚注 / 4 处经文），已镜像至 `latest translations/BWV_4/`。

---

## [1.0.1] - 2026-08-18（补丁小更）

### 🩹 Patch Note（补丁说明）

本次补丁解决一个影响**所有对话康塔塔**（如 BWV 60、71、140 等含角色对话的作品）的脚注超链接错位问题，并修正归档文档的时间戳语义。

**问题背景**：对话康塔塔的歌词里，角色名（如「恐惧 Furcht」「希望 Hoffnung」「基督 Christus」）以独立标签行穿插在歌词行之间；而学术脚注的编号本应对齐到「不含角色标签」的歌词行。旧代码在多个环节混用了两种索引，导致脚注上标 `[N]` 锚点整体错位——读者点击某行歌词的脚注编号，跳转到的却是另一行对应的注释。

**修复内容**（三层根因，逐层修复）：

| 层 | 文件 | 根因 | 修复 |
|----|------|------|------|
| step4 | `pipeline/step4_translate.py` | 用含角色标签的数组索引直接访问脚注列表 | 维护 `non_role_idx` 计数器，角色标签行不计脚注 |
| step1 | `pipeline/step1_uofa.py` | 成对语气词合并时用含角色标签的索引访问英文/脚注 | 同上改用 `non_role_idx` |
| step1 | `pipeline/step1_fetch_texts.py` | 英文文本含角色名残留（"Fear"/"Hope"），且脚注分散在德语/英语两块 | 重构：合并 de+en 两块的 `<sup>N</sup>` 脚注标记，清理角色名残留 |

**修复效果**：BWV 60 的 27 条脚注中 24 条自动正确对齐（修复前几乎全部错位）。剩余 3 条（fn11/19/20）因数据源 bachcantatatexts.org 与 UAlberta 的歌词分行偶有差异（个别长句合行），仍存在 1 行偏差，属数据源限制，已在「已知限制」中注明。

### Fixed（修复）

- 修复对话康塔塔脚注超链接错位（三层根因，详见上文 Patch Note）。

### Changed（变更）

- **归档时间戳改用文件修改时间**：`_archive_existing_docx`（康塔塔与众赞歌两处）由「生成新译文的当前时间」改为「被归档文件的最后修改时间（mtime）」，使历史归档忠实反映旧译文的实际修改时刻。
- **重写 README**：改为四部分结构——① 中英双语功能总览（康塔塔翻译 / 众赞歌翻译 / 共享术语库）；② 翻译流程与已上传译文展示；③ Skill 部署安装与本地 Agent 工具适配（WorkBuddy / Claude Code / Cursor / Windsurf / 通义灵码等）；④ 使用方法。其余沿用发布版内容。

### Added（新增）

- 新增 BWV 60《O Ewigkeit, du Donnerwort》完整翻译（对话康塔塔，5 乐章 / 27 脚注 / 10 处经文），德中对照 docx + 纯中文 txt 已入库 `latest translations/BWV_60/`。

### 数据修正

- 11 个历史归档 docx 的文件名时间戳重命名为其实际修改时间（含 BWV 140 的非标准后缀「新」→ `20260731_223150`）。

---

## [1.0.0] - 2026-08-16（正式发布）

### Added（新增）

- **首次公开发布至 GitHub**：仓库 `2129084619-cmd/bach-cantata-Chinese-translator`（公开 / MIT / main 分支）。
- **SKILL.md 发布版**：去除 6 处硬编码绝对路径，改用可移植的 `python` / `pip` 命令。
- **README.md**：中英两版简介，注明「仅简体中文版本」「AI 辅助翻译」「数据来源版权声明」。
- **LICENSE**（MIT）、**requirements.txt**（补齐 beautifulsoup4 / openpyxl / lxml / pdfplumber）、**.gitignore**（排除产物、日志、缓存与一次性脚本）。

### 入库内容

- `pipeline/`（17 个 .py）、众赞歌子系统（含索引 + 14 首数据 + 最新译文）、`latest translations/`（BWV 1 / 2 / 194）、共享术语库 xlsx、IMSLP 声乐作品索引。

---

## [0.4.0] - 2026-08-16

### Added（新增）

- **圣经经文搜索流程重构**：经文清单统一从基本信息源（bach-cantatas.com Epistle/Gospel + bachipedia.org）按 BWV 检索；新增 Step 3.5 众赞歌→经文模糊搜索（`step35_chorale_bible.py`）。
- **译文输出位置重构**：docx/txt 统一写入 `raw data & all translations/BWV_N/`，并镜像到 `latest translations/BWV_N/`；重译时旧 docx 自动归档保留历史。
- **众赞歌归档与镜像**：`latest translation/` 只存最新 docx，旧版归档到 `translation archive/<ChoraleNNN>/`。
- 新增翻译：BWV 195、BWV 2、BWV 194；BWV 1 按新输出规则重新翻译。

### Fixed（修复）

- 修复经文引用连字符归一化（en-dash / em-dash 统一为连字符，消除重复条目）。
- 修复众赞歌复用跨源分行差异（`Amen! Amen!` 拆/合导致的错位）。
- 修复 `write_cantata_translations` 角色行粗体丢失（只替换占位符、保留粗体角色名）。

---

## [0.3.0] - 2026-08-03 ~ 08-05

### Added（新增）

- **翻译原则升级至 v3.x**：语义准确性优先、行数强制一致、行内句意不碎片化、相邻行不重复、成对词语不拆分、术语对齐和合本。
- **数据源优先级重构**：UAlberta 为德语歌词主源，kantate.info（NBA 精校文本）为回退源，bachcantatatexts.org 仅作脚注/注释参考。
- **跨源角色交叉验证机制**：对话康塔塔角色名→声部映射自动检测。
- 新增翻译：BWV 147、BWV 49、BWV 60、BWV 21、BWV 54。

### Fixed（修复）

- 修复众赞歌检测系统漏检（BWV 147、BWV 60 等）。
- 修复 BWV 49 触发的管线 bug。

---

## [0.2.0] - 2026-07-31 ~ 08-01

### Added（新增）

- **对话康塔塔支持**（管线 v2.2.0）：角色标签识别、管道分隔二重唱文本、字体标准化、合并 Docx（基本信息表 + 德中对照 + 尾注）。
- **众赞歌翻译管理子系统首次实现**：BWV→众赞歌映射索引、详情抓取、翻译 API、Step 4.5 众赞歌复用。
- **共享术语库**：宗教术语统一管理于 `巴赫康塔塔术语库.xlsx`。
- 新增翻译：BWV 140、BWV 49；众赞歌 Chorale015、Chorale026。

### Fixed（修复）

- 修复 Docx 标题取第一乐章而非整体标题。
- 修复众赞歌 docx 换行、基本信息表与声乐作品表填充。

---

## [0.1.0] - 2026-07-30

### Added（新增）

- 项目起步：完成 BWV 1《Wie schön leuchtet der Morgenstern》完整翻译（德语歌词 + 英文翻译 + 30 条学术脚注）。
- 创建 WorkBuddy Skill「巴赫康塔塔歌词翻译」。
- 用 Skill 完整跑通 BWV 71《Gott ist mein König》（7 乐章 / 28 脚注）。

---

## 版本命名说明

- **0.1.0 ~ 0.4.0**：正式发布前的开发版本，功能持续累积、接口可能变动。
- **1.0.0**：首次公开正式发布。
- **1.0.1**：正式发布后的首个补丁（本次）。
