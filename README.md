# chatgpt-document

从 AI 对话记录（ChatGPT、Gemini、Perplexity）抓取或导入内容，经大模型分类整理、生成深度报告，支持报告 1.0 → 专家评审 → 报告 2.0 → 报告 3.0 最终版 → 报告 4.0（事实核查与引用）。

## 核心特性

- **多 API 支持**：Kimi、OpenAI、Grok、Perplexity、Claude、Gemini，可切换或指定 Provider
- **本地文档语料合并**：读取目录下 Word/PDF/图片等，经 API 去重排序后生成报告 3.0
- **图片与公式提取**：网页爬虫自动提取图片和公式（KaTeX/MathJax/Unicode 数学字符），DOCX/PDF 提取嵌入图片和 OMML 公式
- **公式端到端支持**：LaTeX 公式从语料采集到 Word 导出全程保留，Word 中渲染为原生数学对象
- **学术场景增强**：内置研究计划、论文大纲、算法实验计划三种学术报告类型，各配 5 位定制评审专家

## 环境要求

- Python 3.8+
- 任一 API Key：Kimi / OpenAI / Grok / Perplexity / Anthropic / Google Gemini

## 安装

```bash
cd D:\BaiduSyncdisk\aicoding\chatgpt-document
pip install -r requirements.txt
```

首次使用 Pyppeteer 时会自动下载 Chromium，请保持网络畅通。

## 配置：多 API 接口

复制 `.env.example` 为 `.env`，填入所需 API Key：

| Provider | 环境变量 | 获取地址 |
|----------|----------|----------|
| kimi | KIMI_API_KEY | [Moonshot 开放平台](https://platform.moonshot.cn)（默认） |
| openai | OPENAI_API_KEY | [OpenAI](https://platform.openai.com) |
| grok | GROK_API_KEY | [xAI](https://x.ai) |
| perplexity | PERPLEXITY_API_KEY | [Perplexity](https://www.perplexity.ai/settings/api) |
| claude | ANTHROPIC_API_KEY | [Anthropic](https://console.anthropic.com)（需 `pip install anthropic`） |
| gemini | GEMINI_API_KEY | [Google AI Studio](https://aistudio.google.com)（需 `pip install google-generativeai`） |

- 在 `.env` 中设置 `LLM_PROVIDER=gemini`（或 openai、kimi 等）选择默认 Provider
- 命令行可覆盖：`python main.py batch ./语料目录 -o 输出名 -p gemini`

---

## 程序流程总览

### 一、主流程（推荐）

```
all：全流程一条龙
导入/抓取 → Step1 采集 → Step2 报告1.0 → Step3 专家评审 → Step4 报告2.0 → Step5 报告3.0 最终版
```

| 阶段 | 命令 | 输入 | 输出 |
|------|------|------|------|
| Step1 | fetch | 分享链接或本地文件 | `output/raw/{name}.txt` |
| Step2 | report-v1 | 原始语料 | `output/reports/{name}_report_v1.md`、`.docx`、`_meta.json` |
| Step3 | experts | 报告1.0 | 五位专家意见、幻觉清单、专家意见汇总 |
| Step4 | report-v2 | 报告1.0 + 专家意见 + 原始语料 | `output/reports/{name}_report_v2.md`、`.docx` |
| Step5 | report-final | 报告2.0 + 原始语料 | `output/reports/{name}_report_v3.md`、`.docx` |
| Step6 | report-v4 | 报告3.0 | `output/reports/{name}_report_v4.md`、`.docx`（含 References 引用） |
| Step7（可选） | report-policy | 原始语料 + 最新报告 | `output/reports/{name}_学术风格分析报告.md`、`.docx` |
| Step8 | report-v5 | Step7 学术风格分析报告 | `output/reports/{name}_报告_v5.md`、`.docx`（Prompt RL 迭代压缩） |

### 二、本地文档语料合并（merge / batch）

当有多份语料文件（Word、PDF、图片等）存放在同一目录时，可先进行合并重整，再进入报告流程。

| 阶段 | 命令 | 输入 | 输出 |
|------|------|------|------|
| Step0 | merge | 本地目录路径 | `output/raw/{name}.txt`（去重、排序后的合本） |
| 全流程 | batch | 本地目录路径 | Step0 → 1.0 → 专家 → 2.0 → 3.0 |

**merge**：读取目录下所有语料，调用云端大模型 API 进行去重、排序，输出合成本地语料。  
**支持格式**：
- 文本：.txt / .md / .json / .html
- Word：.docx
- PDF：.pdf
- 图片：.jpg / .png / .gif / .webp / .bmp（提交云端 Vision API 处理）

**batch**：一步完成「目录语料合并 + 报告 1.0 + 专家评审 + 报告 2.0 + 报告 3.0 最终版」。

```bash
# 仅重整语料（输出到 output/raw/xxx.txt）
python main.py merge ./my_corpus_dir -o 输出名 -r

# 重整 + 全流程 1.0→2.0→3.0，并指定 API Provider
python main.py batch ./my_corpus_dir -o 输出名 -r -s A -p gemini
```

`-r` 递归读取子目录；`-p gemini` 指定使用 Gemini API（也可为 openai、kimi 等）。

### 三、各步骤详解

#### Step1 采集（fetch / crawl / import）

- **fetch**：统一入口，自动识别 URL 或本地文件
- **crawl**：仅抓取分享链接（ChatGPT / Gemini / Perplexity）
- **import**：仅导入本地文件（.txt / .json / .md）
- **输出**：`output/raw/{name}.txt`

#### Step2 报告 1.0（report-v1）

1. 调用 Kimi API 分析语料 → 生成大纲（≤7 章、≤3 级目录）
2. 按章节装配原始语料到各章（多段分块）
3. 每章添加章首描述、章末总结（承上启下）
4. 对比原始语料与报告，补充遗漏内容
5. 去重
6. 输出 Markdown 与 Word

**输出**：`{name}_report_v1.md`、`{name}_report_v1.docx`、`{name}_meta.json`

#### Step3 专家评审（experts）

五位专家分别评审：

| 专家 | 职责 |
|------|------|
| 专家1 | 事实与逻辑 |
| 专家2 | 结构与深度（建议采用三段论、递进推理、多角度对比、动机理论等表达模式） |
| 专家3 | 可行性与合规 |
| 专家4 | 事实核查（调用 Perplexity 检索核实），输出**幻觉清单**及有事实依据的修改意见 |
| 专家5 | 文笔与风格，去除 AI 味 |

**输出**：`output/experts/{name}_专家{1-5}_*.md`、`{name}_专家4_幻觉清单.md`、`{name}_专家意见汇总.md`

#### Step4 报告 2.0（report-v2）

- **输入**：报告 1.0 + 专家意见汇总 + 幻觉清单 + 原始语料
- **处理**：分章整改，按专家意见修订，删除幻觉，篇幅目标 ≥ 原始语料 60%
- **输出**：`{name}_report_v2.md`、`{name}_report_v2.docx`

#### Step5 报告 3.0 最终版（report-final）

- **输入**：报告 2.0 + 原始语料（必填，用于幻觉校验）
- **处理**：列表改自然叙述、应用文档风格、剔除未在原始语料出现的内容
- **风格**：A=商业模式设计报告；B=可行性研究报告；C=学术综述
- **输出**：`{name}_report_v3.md`、`{name}_report_v3.docx`

#### Step6 报告 4.0（report-v4）— 事实核查与引用

- **输入**：报告 3.0 路径（支持 `.md` 或 `.docx`）
- **处理**：按章节将内容提交 **Perplexity API**，自动分析实体、事件、数据等事实并标注出处 → 在正文插入 `[n]` 引用标记 → 文末生成 References 列表（调用次数 = 章节数）
- **依赖**：需配置 `PERPLEXITY_API_KEY`（.env），Perplexity 模型默认 `sonar`
- **输出**：`{name}_report_v4.md`、`{name}_report_v4.docx`

#### Step7（可选）学术风格分析报告（report-policy）

- **输入**：原始语料（如 `output/raw/gaojinsumei.txt`）+ 最新版报告（如 `output/reports/gaojinsumei_report_v4.docx`）
- **处理**：采用 `output/skill/{policy}/Skill.md` 与 `summary.md` 进行风格化，输出学术风格分析报告
- **依赖**：需配置 `GEMINI_API_KEY`（.env），调用 Gemini API
- **输出**：`{name}_学术风格分析报告.md`、`{name}_学术风格分析报告.docx`

```bash
python main.py report-policy gaojinsumei.txt gaojinsumei_report_v4.docx -o gaojinsumei -p policy1
```

#### Step8 报告 5.0（report-v5）— Prompt RL 迭代压缩

- **输入**：Step7 学术风格分析报告（.md 或 .docx）
- **处理**：采用 Prompt RL 方式迭代压缩；每轮压缩≥10%，最多 4 轮，最终尺寸≥原始 50%；保留事实与分析逻辑，遵循 Skill 规范
- **依赖**：`GEMINI_API_KEY`
- **输出**：`{name}_报告_v5.md`、`.docx`

```bash
python main.py report-v5 gaojinsumei_学术风格分析报告.docx -o gaojinsumei -p policy1
```

### 四、输出目录结构

```
output/
├── raw/          # 原始语料
├── reports/      # 报告 1.0 / 2.0 / 3.0 / 4.0 / 学术风格分析报告（.md / .docx）
├── experts/      # 专家意见
└── skill/        # Step7 风格化 Skill（如 policy1/Skill.md、summary.md）
```

---

## 使用方式

### 一键全流程

```bash
# 从分享链接或本地文件
python main.py all "分享链接或本地文件路径" -o 输出名 -s A -p gemini

# -p 指定 API：gemini | openai | kimi | grok | perplexity | claude
# -s 指定报告3.0风格：A=商业模式设计报告, B=可行性研究报告, C=学术综述
```

### 分步执行

```bash
# Step1：导入/抓取
python main.py fetch "分享链接或本地文件路径" -o 输出名

# Step2：报告 1.0
python main.py report-v1 output/raw/xxx.txt -o xxx

# Step3：五位专家评审
python main.py experts output/reports/xxx_report_v1.md -o xxx

# Step4：报告 2.0
python main.py report-v2 output/reports/xxx_report_v1.md -r output/raw/xxx.txt -o xxx

# Step5：报告 3.0 最终版（必须传入原始语料用于幻觉校验）
python main.py report-final output/reports/xxx_report_v2.md -r output/raw/xxx.txt -o xxx -s A

# Step6：报告 4.0（事实核查与引用，需配置 PERPLEXITY_API_KEY）
python main.py report-v4 output/reports/xxx_report_v3.md -o xxx
# 或使用 .docx 输入：
python main.py report-v4 output/reports/xxx_report_v3.docx -o xxx
```

---

## 支持的数据源

| 平台 | 方式 | 说明 |
|------|------|------|
| ChatGPT | 分享链接 | `chatgpt.com/share/xxx` |
| Gemini | 分享链接 | `g.co/gemini/share` 或 `gemini.google.com` |
| Perplexity | 分享链接 | `perplexity.ai` |
| 任意 | 本地文件 | `.txt` / `.json` / `.md`（导出或复制粘贴） |

---

## 其他命令

| 命令 | 说明 |
|------|------|
| **merge** | 本地文档语料合并：读取目录下 Word/PDF/图片等，经 API 去重排序后合成为 output/raw/xxx.txt |
| **batch** | 目录语料重整 + 全流程（1.0 → 专家 → 2.0 → 3.0），支持 `-p` 指定 API |
| **report-v4** | 对报告 3.0 做事实核查与引用，调用 Perplexity 获取出处，生成 4.0（含 References） |
| **report-policy** | Step7（可选）：根据原始语料与最新报告，采用 Skill/summary 风格化，输出学术风格分析报告（Gemini API） |
| **all-v3** | fetch → report-v3（从原始语料直接生成 3.0，不走专家流程） |
| **all-context** | 多轮 Kimi 会话（保持记忆）→ 1.0 → 专家 → 2.0 |
| **install-browser** | 安装 Playwright Chromium（爬虫备用） |

---

## 注意事项

- **ChatGPT 分享页**：若页面结构更新，可能需在 `src/step1_crawler.py` 中调整选择器。
- **内容不足重试**：若多次重试后仍不足 1000 字节，程序仍会保存当前内容并给出警告。
- **Kimi 模型**：默认 `kimi-k2-turbo-preview`，可在 `.env` 中改为 `kimi-latest` 等。
- **长文本**：Step2/Step4 会对过长内容做截断，以保证在模型上下文限制内。
- **output 目录**：已在 `.gitignore` 中，不会提交到版本库。

---

## 更新日志

### v3.0 — 图片与公式提取 + 学术场景增强（2026-03-11）

本次更新包含三大模块：**富媒体语料提取基础设施**、**学术场景全链路增强**、**文档公式端到端支持**。

#### 一、富媒体语料提取（CorpusPackage）

引入"语料包"目录格式，替代单一 `.txt` 文件，当检测到图片或公式时自动启用：

```
output/raw/{name}/
  corpus.md        # 主文本（含 ![img](assets/...) 和 $latex$ 占位符）
  manifest.json    # 元信息：来源 URL、时间戳、资产列表
  assets/          # 下载的图片文件
```

| 能力 | 说明 |
|------|------|
| **网页图片提取** | 爬虫 DOM 遍历提取 `<img>` 标签，浏览器内 `fetch()` 下载（保留 cookies/CORS） |
| **网页公式提取** | 支持 KaTeX（`.katex` + `annotation`）、MathJax v2（`script[type="math/tex"]`）、MathJax v3（`mjx-container`） |
| **Unicode 数学字符识别** | ChatGPT 分享页使用 Unicode 数学字符（U+1D400-1D7FF）渲染公式，自动检测并转换为 LaTeX `$...$` 标记 |
| **DOCX 图片提取** | 解析 Word 文档 XML 中的 `wp:inline`/`wp:anchor` 绘图元素，提取嵌入图片 |
| **DOCX 公式提取** | 解析 `m:oMath`/`m:oMathPara` OMML 元素，递归转换为 LaTeX（支持分数、上下标、根号、矩阵等） |
| **PDF 图片提取** | 使用 pypdf `page.images` API 提取 PDF 嵌入图片 |
| **Step0 语料合并** | 合并多文件时自动收集图片资产，跨文件重编号，有图片时输出语料包格式 |
| **向后兼容** | 纯文本爬取仍输出 `.txt`；`load_raw_content()` 统一处理两种格式，下游 Step2-8 无需改动 |

#### 二、公式端到端支持（Phase A）

确保公式从语料采集到最终 Word 文档的完整保留：

- **LLM 提示词注入**：Step2/4/5/7/8 共 12 处 prompt 添加公式保留指令（`$...$` 和 `$$...$$` 不修改）
- **DOCX 公式渲染**：Word 导出时解析 LaTeX 公式，通过 LaTeX→OMML 转换器插入为 Word 原生数学对象
- **LaTeX↔OMML 双向转换**：`src/utils/omml_converter.py` 支持 `\frac`、`\sqrt`、`\sum`、`\int`、希腊字母、矩阵、对齐方程等

#### 三、学术场景增强（Phase B）

新增三种学术报告类型，各配备 5 位定制化评审专家：

| 报告类型 | 配置文件 | 适用场景 |
|----------|----------|----------|
| `research_plan` | `output/skill/report_types/research_plan.md` | 科研项目计划与研究方案 |
| `paper_outline` | `output/skill/report_types/paper_outline.md` | 论文写作大纲与结构规划 |
| `experiment_plan` | `output/skill/report_types/experiment_plan.md` | 算法实验设计与开发计划 |

- **学术 Skill 升级**：`policy_academic_research/Skill.md` 扩展至 85 行，覆盖结构规范、论证标准、数学公式规范、元认知框架
- **专家面板定制**：每种报告类型的 5 位专家针对该场景（如论文评审的"技术贡献"专家、实验计划的"科学严谨性"专家）

#### 四、学术引用增强（Phase C）

- **作者-年份引用格式**：`run_report_v4(citation_style="author_year")` 支持 `[1] Author (Year). Title. URL`
- **DOCX 引用上标渲染**：正文中 `[N]` 引用标记在 Word 中渲染为上标格式
- **Perplexity 学术偏好**：提示词优先使用 DOI/arXiv 链接、权威学术来源，公式保留指令

### v2.0 — 14 项文档能力优化（3.1-3.14）

#### 核心管线增强

| 编号 | 特性 | 说明 |
|------|------|------|
| 3.1 | **全文一致性校验** | 新增 `step4b_consistency_check.py`，检查跨章节重复、矛盾、缺失过渡、篇幅失衡 |
| 3.2 | **大纲迭代优化** | 大纲构建后 API 审阅覆盖度、独立性、逻辑递进、均衡性 |
| 3.3 | **专家意见冲突调和** | 仲裁环节按事实>结构>风格优先级裁定采纳/搁置/折中 |
| 3.4 | **智能篇幅分配** | 大纲加 density 权重，Step4 按密度加权分配各章目标字数 |
| 3.5 | **Word 导出增强** | 支持超链接、引用块、嵌套列表、水平线、代码块、图片、表格对齐、目录、页眉页脚、封面页、脚注 |
| 3.6 | **章节上下文传递** | Step4/5/7 改写时注入全文目录和前后章摘要，增强跨章衔接 |

#### 高级功能

| 编号 | 特性 | 说明 |
|------|------|------|
| 3.7 | **断点续跑** | `full-report` 支持中断恢复，`--no-resume` 可强制重跑 |
| 3.8 | **输出质量评分** | `quality-eval` 子命令多维度评估报告质量 |
| 3.9 | **引用验证** | Step6 后并行 HEAD 检查引用 URL，不可达标记 `[N 待验证]` |
| 3.10 | **多格式导出** | 支持 HTML/PDF 导出及 `export` 子命令 |
| 3.11 | **语义漂移检测** | 比较报告版本间核心论点变化 |
| 3.12 | **交互式审阅** | `--interactive` 在大纲/仲裁/风格选择处暂停确认 |
| 3.13 | **多语言支持** | `--lang zh/en`，Word 字体按语言选择 |
| 3.14 | **报告模板系统** | profile 扩展 min/max_chapters、min_total_chars、default_style，大纲生成注入模板约束 |

#### 代码质量

- 统一错误处理：提取 `save_docx_safe()` 消除 7 处重复
- 集中系统提示词到 `src/prompts.py`
- 提取 `_run_standard_pipeline()` 合并 3 条重复流程
- 清理 11 个文件的未使用 import

## 许可证

按项目需要自行选择。
