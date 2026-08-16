# 巴赫康塔塔歌词翻译

## 用法

```文本
/巴赫康塔塔歌词翻译 1                  → 翻译 BWV 1（康塔塔完整管线）
/巴赫康塔塔歌词翻译 chorale 4          → 查询并弹出 BWV 4 对应众赞歌 docx
/巴赫康塔塔歌词翻译 chorale 4 --翻译    → 手动翻译 BWV 4 对应众赞歌（也可用 ——翻译 或 -翻译）
/巴赫康塔塔歌词翻译 update             → 更新后端管线代码
```



> **注意**：`--翻译` 中的 `--` 为 ASCII 半角双连字符（U+002D）。若用户使用全角破折号 `——` 也视为等价，二者均触发翻译流程。单连字符 `-翻译` 同样有效。

当用户输入 `chorale <BWV>` 或任何众赞歌相关请求时，跳过康塔塔管线，进入「众赞歌翻译管理子系统」流程。  
当用户输入纯 BWV 编号（如 `1`、`18`）时，走康塔塔完整管线（Step A ~ F）。

## 共享术语库

所有康塔塔的宗教术语统一管理在：`巴赫康塔塔术语库.xlsx`（工作空间根目录）

- **列**：原文术语(德语) / 译文术语(中文和合本) / 所属康塔塔编号 / 出现频次 / 备注说明
- **自动更新**：Step A 管线运行时，`glossary_db.update_from_glossary()` 自动追加新术语、更新频次
- **译法差异**：同一术语在不同康塔塔有不同译法时，备注列自动标注
- **翻译时使用**：Step D 必须读取此 Excel 以确保术语统一

## 翻译管线完整流程

当用户输入 BWV 编号（如 `1`）时，执行以下全部步骤：

### Step A0 — IMSLP 声乐作品预检

管线启动时自动调用 `pipeline/imslp_index.py` 中的 `assert_vocal(bwv)`：

- 查询 `bach_vocal_index.json`（来自 imslp.org 巴赫作品表，690 条声乐作品记录）
- 若 BWV 不在索引中 → 拒绝执行，输出 `BWV {N} 不是巴赫声乐作品`
- 若在索引中 → 继续执行后续步骤

索引构建（首次自动运行）：

```bash
python -m pipeline.imslp_index --force
```

### Step A — 运行 Python 管线

```bash
python -m pipeline.main {BWV} --force
```

确认 step0 ~ step4 全部返回 `ok`。产出：

- `raw data & all translations/BWV_{N}/data/` — JSON 中间数据（含 `chorale_reuse_manifest.json`）
- `raw data & all translations/BWV_{N}/BWV{N}_德中对照译文.docx` — **合并 Docx**（含基本信息表 + 德中逐行对照 + 尾注，中文为【待翻译】）
- `latest translations/BWV_{N}/` — 最新 docx/txt 的镜像目录（Step E 完成后回填）
- `巴赫康塔塔术语库.xlsx` — 术语自动同步更新
- Docx1（单独的原文与验证）已废弃，基本信息表合并到 Docx 中

> **输出位置规则（2026-08-16 起）**：译文 docx/txt 一律写入 `raw data & all translations/BWV_{N}/`（**不再**写入工作空间根目录）。Step E 完成后调用 `mirror_to_latest()` 把最新 docx/txt 镜像到 `latest translations/BWV_{N}/`。**重新翻译已完成的康塔塔时**，管线在覆盖前会自动把旧 docx 归档为 `BWV{N}_德中对照译文_{时间戳}.docx`，保留历史版本；txt 允许直接覆盖。

Step 4.5（众赞歌复用）在 step4 后自动运行：

1. 扫描 `texts.json` 中 `type="chorale"` 的乐章
2. 查找 `chorale_index.json` → `ChoraleNNN.json` 中 `chinese_text` 是否有现成译文
3. 生成 `raw data & all translations/BWV_{N}/data/chorale_reuse_manifest.json`，标记每个乐章为 `filled` / `needs_translation` / `no_match`
4. filled 的乐章在 Step D 翻译时直接复制已有译文，无需重新翻译
5. **needs_translation 或 no_match 的乐章：必须在 Step D 翻译完成后，强制触发众赞歌翻译子系统**（`/巴赫康塔塔歌词翻译 chorale {BWV} --翻译`），确保众赞歌译文同步生成并回填至 JSON 供后续复用

> **强制规则**：只要 `chorale_reuse_manifest.json` 中存在 `needs_translation` 或 `no_match` 状态的众赞歌乐章，康塔塔翻译流程结束前必须触发众赞歌翻译子系统。不可跳过。

> 注意：部分 BWV 编号（如 71、140）的 bachcantatatexts.org JSON 中英文行不含 `[N]` 上标标记，因此 Docx 模板**不含**超链接（bookmark 存在但无 hyperlink）。Step E2 会处理超链接注入。

> **对话康塔塔**：step1 自动检测角色标签（Seele/Jesus 等）和管道分隔二重唱文本（`Eröffne|Ich öffne`）。Docx 中角色标签以灰色斜体加粗渲染。

### Step B — 填充中文和合本经文

> **圣经经文搜索来源（2026-08-16 起）**：经文清单**不再**来自 bachcantatatexts.org 脚注。统一流程为：
>
> 1. Step 2 从基本信息源（bach-cantatas.com 的 Epistle/Gospel + bachipedia.org/werke/）按 BWV 编号抓取对应经课（epistles / readings）
> 2. Step 3.5 众赞歌模糊搜索：经 `chorale_index.json` 建索引 → 交叉搜索权威众赞歌站点（hymnary.org 等）+ 内置曲目表，查明每部众赞歌的写作来源（如「Ach Gott vom Himmel sieh darein」出自诗篇 12）→ 关联康塔塔/众赞歌歌词 → 匹配对应圣经文本
> 3. Step 3 汇总以上来源，生成 `bible_cn_manifest.json`

1. 读取 `raw data & all translations/BWV_{N}/data/bible_cn_manifest.json`
2. 对每条 reference，用 **WebFetch** 从 BibleGateway 获取中文和合本 (CUVS)：
   ```
   URL: https://www.biblegateway.com/passage/?search={book}+{chapter}%3A{verse}&version=CUVS
   ```
3. 填入 `verses_text` 字段，设 `retrieved: true`
4. 保存更新后的 manifest
5. 用 3-5 并发 WebFetch 加速

> **众赞歌经文模糊搜索（Step 3.5）**：`pipeline/step35_chorale_bible.py` 按「内置曲目表 → 众赞歌数据 author 字段解析（based on Psalm N）→ bach-cantatas.com 众赞歌详情页」三级快速解析，结果缓存至 `巴赫康塔塔中的众赞歌/chorale_bible_sources.json`。hymnary.org 有反爬验证，仅作为 AI WebFetch 的最后兜底，不在管线内直接抓取。

### Step C — 重建翻译上下文

```bash
python -c "
import sys, json; sys.path.insert(0, '.')
with open('raw data & all translations/BWV_{N}/data/texts.json','r',encoding='utf-8') as f: texts=json.load(f)
with open('raw data & all translations/BWV_{N}/data/footnotes.json','r',encoding='utf-8') as f: footnotes=json.load(f)
with open('raw data & all translations/BWV_{N}/data/glossary.json','r',encoding='utf-8') as f: glossary=json.load(f)
with open('raw data & all translations/BWV_{N}/data/bible_cn_manifest.json','r',encoding='utf-8') as f: bible_cn=json.load(f)
with open('raw data & all translations/BWV_{N}/data/luther_verify.json','r',encoding='utf-8') as f: luther_verify=json.load(f)
with open('raw data & all translations/BWV_{N}/data/metadata.json','r',encoding='utf-8') as f: metadata=json.load(f)
from pipeline import step4_translate
result=step4_translate.run({N}, texts['movements'], footnotes, glossary, bible_cn, luther_verify, metadata, 'raw data & all translations/BWV_{N}')
print(f'Updated: {len(result[\"context\"][\"lines\"])} lines')
"
```

### Step D — AI 中文翻译

1. 读取翻译上下文 `translation_context.json`
2. 读取当前康塔塔术语 `glossary.json`
3. 读取共享术语库 `巴赫康塔塔术语库.xlsx`（`pipeline.glossary_db.load_terms()`）
4. 阅读学术脚注 `footnotes.json`
5. **以乐章为单位逐乐章翻译**，对每个乐章读取其完整德语原文，综合以下信息：
   - 德语原文 (`german`) — 核心依据
   - 中文和合本经文 (`relevant_bible_cn`) — 核心依据
   - 对应脚注（按 `footnote_ids` 查找）
   - ~~英文翻译 (`english`)~~ — **不使用**（bachcantatatexts.org 英文仅作注释素材，不参与译文参考）
   - 和合本术语库确保译法一致
6. **翻译规则（v3.2 重构）**：
   - 【最高优先级】核心依据：德语原文 + 中文和合本 (CUV) → **语义准确性优先**
   - **不使用英文译文作翻译参考**（bachcantatatexts.org 英文译文仅作注释翻译素材）
   - **行数强制一致**：每个乐章/诗节的德语行数 = 中文行数。不可合并或拆分行导致总数偏差（如 10 行德语必须输出 10 行中文）
   - **行内句意不可碎片化**：在保证行数一致的前提下，每行中文应承载独立、完整的意群，避免将一个完整句子机械切分成多行无意义的碎片。跨行意译是允许的（如德语第 3 行的"火焰"可在中文第 1-2 行提前引入），但每行应有可辨识的语义
   - **相邻行不可重复**：前后行不可承载相同或近似的句意（如上一行"心因爱受伤"、下一行"心被爱刺透"），应让每行推进文本
   - **成对词语不可拆分**：`Eia, eia`、`Amen! Amen!`、`Singet, springet` 等成对语气词/动词必须合为一行中文，拆成两行会导致后续全部错位
   - **乐章整体语义优先**：每个乐章视为完整语义单元，优先保障意群内部的逻辑连贯性
   - 宗教专有名词严格对齐术语库中的和合本译法
   - 须补充的神学/文化背景说明（超出和合本范围）以方括号 [注：...] 标注，与正文区分
   - 优先级：和合本一致性 > 乐章语义完整性 > 意群逻辑连贯性 > 诗歌性 > 音乐节奏
   - 脚注中提到的圣经典故，若经文已获取，在翻译中体现其语境
   - 路德宗神学概念（如圣餐 "in, mit und unter"）需准确传达
7. **注释翻译（必做，不可跳过）**：逐条将 `footnotes.json` 中每条注释翻译为通顺中文，保留学术严谨性，调用 `translate_footnotes_in_docx()` 写入。该函数会**自动在每条译文后追加「内容仅供参考」**（脚注源自 bachcantatatexts.org，仅作参考）。**翻译完成后必须调用 `check_untranslated_footnotes(docx_path)` 验证，若 untranslated > 0，必须重新翻译直至清零。**

### Step E — 生成最终 Docx（含翻译 + 尾注）

Docx 采用**段落格式**，字体规范统一：

- **标题/乐章标题**：Times New Roman 加粗
- **德语歌词正文**：Times New Roman **不加粗**，11pt
- **中文译文正文**：宋体**不加粗**，11pt（务必设置 `eastAsia=宋体`），黑色
- **对话角色标签**（如 Seele、Jesus）：Times New Roman 加粗，11pt（与中文译文同行）
- 尾注文本：9pt

Docx 模板已包含【待翻译】占位符。Step E 用 python-docx 替换占位符为中文译文。每个占位符替换为一个中文译文字符串，中文行数无需与德语行数严格一致。

替换占位符时**必须设置中文字体和黑色**：

```python
r.font.name = 'Times New Roman'
r.font.size = Pt(11)
r.bold = False
r.italic = False
r.font.color.rgb = RGBColor(0, 0, 0)  # 必须设为黑色
rPr = r._r.get_or_add_rPr()
rFonts = rPr.find(qn('w:rFonts'))
if rFonts is None:
    rFonts = OxmlElement('w:rFonts')
    rPr.insert(0, rFonts)
rFonts.set(qn('w:eastAsia'), '宋体')
```

**对话康塔塔角色行**：step1 已在 `line_is_role_label` 字段标记。完整角色名列表在 `pipeline/config.py` 的 `DIALOGUE_ROLE_NAMES`（涵盖巴赫全部对话康塔塔、世俗康塔塔、受难曲角色）。Docx 中角色名以 TNR 加粗渲染，与中文译文占位符在同一行（`Seele  【待翻译】`）。翻译时直接替换【待翻译】为中文角色名（如`魂`/`耶稣`）。

**尾注翻译**：管线生成的 Docx 中学术注释为英文原文。完成 Step D 注释翻译后，调用函数写入：

```python
from pipeline.step4_translate import translate_footnotes_in_docx
footnotes_cn = {1: "译文...", 2: "译文...", ...}
translate_footnotes_in_docx('raw data & all translations/BWV_{N}/BWV{N}_德中对照译文.docx', footnotes_cn)
```

### Step E2 — 注入脚注超链接

**检查 Docx2 中是否有超链接**：用 `zipfile` 读取 `word/document.xml`，搜索 `<w:hyperlink`。若为 0（常见于 BWV 71、140 等），需手动注入：

1. 读取 `footnotes.json`，分析每条脚注对应的乐章和行号
2. 构建 `footnote_map = {(movement, line_index): [footnote_ids]}` 映射
3. 调用注入函数：

```bash
python -c "
import sys; sys.path.insert(0, '.')
from pipeline.step4_translate import inject_footnote_hyperlinks
footnote_map = {YOUR_MAPPING}
inject_footnote_hyperlinks('raw data & all translations/BWV_{N}/BWV{N}_德中对照译文.docx', {N}, footnote_map)
print('Hyperlinks injected')
"
```

> `inject_footnote_hyperlinks()` 使用 lxml 在中文段落末尾追加 `<w:hyperlink>` 元素，上标格式（8pt, w:vertAlign=superscript），锚点匹配已有的 `w:bookmarkStart`。

### Step E3 — 导出纯中文译文 TXT + 镜像到 latest translations

用 `write_chinese_txt()` 写入 TXT（覆盖旧 txt），并调用 `mirror_to_latest()` 把最终 docx + txt 镜像到 `latest translations/BWV_{N}/`：

```python
from pipeline.step4_translate import write_chinese_txt, mirror_to_latest

lines = [...]  # 逐行中文译文（AI 填写）
docx_path = 'raw data & all translations/BWV_{N}/BWV{N}_德中对照译文.docx'
folder = 'raw data & all translations/BWV_{N}'

write_chinese_txt({N}, folder, lines)                     # 写 txt（覆盖旧）+ 自动镜像 txt
mirror_to_latest({N}, docx_path=docx_path)                 # 镜像最终 docx 到 latest translations
```

格式：仅乐章序号 + 曲式外文名 + 译文文本，无注释、无德语、无标记。

### Step F — 展示结果

用 `present_files` 展示：

- `latest translations/BWV_{N}/BWV{N}_德中对照译文.docx`（含完整中文翻译 + 中文注释译文 + 上标超链接）
- `latest translations/BWV_{N}/BWV{N}_中文译文.txt`（纯中文，按乐章分段，仅序号 + 曲式 + 译文）

---

## 众赞歌翻译管理子系统

位于 `巴赫康塔塔中的众赞歌/`，独立于康塔塔主管线可单独调用。

### 索引与数据

| 资源          | 路径                                                                  |
| ----------- | ------------------------------------------------------------------- |
| BWV→众赞歌映射索引 | `巴赫康塔塔中的众赞歌/chorale_index.json`（333 首 / 477 个 BWV 映射）               |
| 详情抓取数据      | `巴赫康塔塔中的众赞歌/data/ChoraleNNN.json`                                   |
| 最新译文文档      | `巴赫康塔塔中的众赞歌/latest translation/ChoraleNNN_德中对照译文.docx`              |
| 历史译文归档      | `巴赫康塔塔中的众赞歌/translation archive/ChoraleNNN/`（重新翻译时旧 docx 自动归档，带时间戳） |

> **输出位置规则（2026-08-16 起）**：众赞歌 docx 统一写入 `latest translation/`（只存最新），触发子管线查询/复用也从该目录调用。重新翻译某首众赞歌时，`generate_chorale_docx()` 会先把旧 docx 归档到 `translation archive/<ChoraleNNN>/`（文件名加 `_YYYYMMDD_HHMMSS` 时间戳），保留完整历史。

### chorale \<BWV> — 查询并弹出 .docx

当用户输入 `chorale <BWV>`（不带 `--翻译` 标志）时：

1. 查找索引中 BWV 对应的众赞歌
2. 若数据尚未抓取，自动抓取详情页并生成 docx（含【待翻译】占位符）
3. 若 docx 已存在，直接 `os.startfile` 弹出（Windows 默认程序打开）
4. 输出众赞歌基本信息：名称、作者、旋律、巴赫采用诗节

执行命令等价于：

```bash
python -m 巴赫康塔塔中的众赞歌.chorale_main {BWV}
```

若 docx 未生成（首次查询），自动抓取：

```bash
python -m 巴赫康塔塔中的众赞歌.chorale_main {BWV} --regenerate
```

### chorale \<BWV> --翻译 — 手动翻译单个众赞歌（含检测与覆盖）

当用户输入 `chorale <BWV> --翻译` 或明确提出翻译众赞歌请求时，**首先调用 `run_translate_pipeline(bwv)`**，该函数自动完成检测→判断→生成三步：

#### 管线流程（`api.run_translate_pipeline(bwv)`）

```
[检测] 查找 BWV {N} 对应的众赞歌
    ↓
[判断] 逐首判定状态：
    ✓ FULL     — docx 已翻译完成 且/或 JSON chinese_text 存在 → [覆盖旧翻译]
    ○ TEMPLATE — docx 模板存在但未翻译，JSON 无中文 → [继续翻译]
    ＋ NEW     — 无任何翻译产物 → [新建翻译]
    ↓
[覆盖/新建] 重新生成 docx（覆盖旧文件，清空为全新占位符）
    ↓
[准备] 打印检测摘要 + 翻译上下文 + 和合本术语指引
    ↓
[返回] context dict，等待 AI 翻译并写回
```

#### 状态日志示例

```
────────────────────────────────────────────────────────────
  [检测] 正在查找 BWV 1 对应的众赞歌...
────────────────────────────────────────────────────────────
  ✓ 找到 1 首众赞歌: Chorale015

  ✓ [FULL    ] Chorale015   [覆盖旧翻译] 已翻译 7/7 诗节 → 重新生成占位符，AI 重新翻译

────────────────────────────────────────────────────────────
  [覆盖] 重新生成 1 首已有翻译的众赞歌 docx...
────────────────────────────────────────────────────────────
  → Chorale015: 覆盖旧翻译，重新生成...
    ✓ docx 已生成: 70/70 占位符 (逐行德中对照)
  [准备完成] 共 70 个占位符，等待 AI 翻译并写回
```

#### AI 执行步骤

1. 调用 `api.run_translate_pipeline(bwv)` → 打印检测 + 覆盖状态 + 翻译上下文
2. **所有状态（FULL / TEMPLATE / NEW）均需 AI 翻译**：
   - FULL 状态：管道已重新生成全新 docx（含 100% 占位符），**旧 JSON 仅作参考**，AI 须以当前 docx 中德语原文为准重新翻译并写回
   - TEMPLATE / NEW 状态：同 FULL，AI 阅读打印的德语原文上下文 → **以诗节为单位翻译**，允许跨行合并意群以保持完整句意 → 构建平展列表 → `write_chorale_translations()` 写回
3. **翻译完成后**：必须将译文同步存入 JSON 的 `chinese_text` 字段（覆盖旧译文），供康塔塔主管线 `step45` 复用
4. **翻译标准（v3.1）**：
   - **行数强制一致**：每个诗节的德语行数 = 中文行数，不可变更
   - **句意不可碎片化 + 相邻行不可重复**：每行承载独立意群，跨行意译允许但忌重复
5. **展示结果**：用 `present_files` 展示更新后的 docx

#### 内部 API（写回）

```python
from 巴赫康塔塔中的众赞歌 import chorale_api as api

# 所有状态均需 AI 新译（FULL/TEMPLATE/NEW）
api.write_chorale_translations('Chorale015', [
    '何其美哉，晨星闪耀，',   # Verse 1 line 1
    '满有恩典和真理，从主而来，',  # Verse 1 line 2
    # ... 所有行平展排列，确保与 docx 占位符总数一致
])

# 写回后同步更新 JSON 缓存（覆盖旧译文）
import json; from datetime import datetime
with open('巴赫康塔塔中的众赞歌/data/Chorale015.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
# data['chinese_text'] = ...  # 更新为新译文
json.dump(data, ...)
```

> **重要**：docx 生成器为每行德语创建独立中文占位符（如 V3 的 7 行德语对应 7 个 `【待翻译】`），而非每节一个占位符。翻译时须将各节译文按行拆分为平展列表传入 `write_chorale_translations()`。

**运行前准备**：确保 Python 环境已安装 `python-docx`, `requests`, `beautifulsoup4`：

```bash
pip install -r requirements.txt
```

### Docx 结构（无英文参考译文）

众赞歌 docx 仅含三个板块：

- **基本信息表** — 众赞歌名称、作者、旋律、作曲家、EKG 编号、主题、巴赫采用诗节
- **巴赫声乐作品使用表** — BWV、乐章号、作品类型、年份
- **德语原文** — 每节标号 + 逐行德中对照（德语一行，紧接中文一行 `【待翻译】`，每行独立占位符）

> 英文参考译文不会出现在生成的 docx 中。德语原文 → 中文译文是唯一对照关系。docx 模板中每行德语后跟一行中文占位符，但翻译时中文行数无需严格等于德语行数——允许跨行整合意群，中文可以自然语序改写为更通顺连贯的表达。写回时仍按平展列表传入 `write_chorale_translations()`，每个占位符对应一行中文。

### 其他 CLI 命令

```bash
# 重建或续建索引
python -m 巴赫康塔塔中的众赞歌.chorale_main --rebuild-index

# 查看索引状态
python -m 巴赫康塔塔中的众赞歌.chorale_main --status

# 直接操作特定众赞歌（按 ID）
python -m 巴赫康塔塔中的众赞歌.chorale_main --chorale-id Chorale012 --regenerate
python -m 巴赫康塔塔中的众赞歌.chorale_main --chorale-id Chorale012 --open-editor
```

### 已知限制

- 部分众赞歌详情页（如 Chorale148）HTML 结构与主流格式不同，诗歌文本提取可能不完整
- 主管线（Step A ~ F）中的 step4 完成时，`chorale_integration.process_bwv(bwv)` 会自动尝试抓取该 BWV 对应的众赞歌数据，但此自动化流程在少数边界情况下可能静默失败

---

## 代码更新接口

当用户输入 `update` 而非 BWV 编号时：

1. 重新读取 `pipeline/` 下全部 `.py` 文件
2. 输出模块摘要：
   - `config.py` — URL 模板和书卷名映射
   - `step0_setup.py` — `run(bwv_number) → folder_path`
   - `step1_fetch_texts.py` — `run(bwv_number) → structured_data`
   - `step2_fetch_bg.py` — `run(bwv_number) → metadata`（含 bachipedia.org readings）
   - `step25_glossary.py` — `run(...) → glossary + luther_verify + docx1`
   - `step3_fetch_bible.py` — `collect_bible_references(metadata, chorale_refs)` + `run(bible_references) → manifest`
   - `step35_chorale_bible.py` — `run(bwv, metadata) → 众赞歌经文模糊搜索引用`
   - `step4_translate.py` — `run(...) → context + docx2`
   - `glossary_db.py` — `update_from_glossary()` + `load_terms()`
3. 提示：「后端代码已刷新，共 N 个模块可用」
4. 不执行翻译流程

---

## 错误处理

- 若任何 step 返回 `error`，记录日志并报告
- 中文经文 WebFetch 失败 → 标记 `retrieved: false`，继续后续
- 翻译时缺上下文 → 仍生成译文，标注 `[注：缺少部分参考信息]`
- **字体问题**：替换【待翻译】时务必设置 `eastAsia=宋体` 且 `bold=False`，中文才会正确渲染
- **超链接缺失**：若 Docx 模板中 `w:hyperlink` 为 0，须执行 Step E2 注入
- **作曲时间空缺**：step2 有 `BWV_COMPOSED_FALLBACK` 回退字典，缺失时添加新条目
- **对话康塔塔**：step1 自动检测角色（Seele/Jesus 等）和管道分隔文本；若检测结果异常，检查 `line_is_role_label`/`line_is_duet` 字段
- **众赞歌抓取**：诗歌文本解析失败（0 节）→ 检查 HTML 页结构，可能需要手动修复 JSON 数据；声乐作品提取缺失 → 确认 chorale_scraper 正则覆盖该页面行格式
- **众赞歌索引**：若 BWV 查不到对应众赞歌 → 运行 `--rebuild-index` 续建索引
