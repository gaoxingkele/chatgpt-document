# chatgpt-document

从 AI 对话记录（ChatGPT、Gemini、Perplexity）抓取或导入内容，经大模型分类整理、生成深度报告，支持报告 1.0 → 专家评审 → 报告 2.0 → 报告 3.0 最终版 → 报告 4.0（事实核查与引用）。

## 核心特性

- **多 API 支持**：Kimi、OpenAI、Grok、Perplexity、Claude、Gemini，可切换或指定 Provider
- **本地文档语料合并**：读取目录下 Word/PDF/图片等，经 API 去重排序后生成报告 3.0

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
| 专家2 | 结构与深度 |
| 专家3 | 可行性与合规 |
| 专家4 | 事实核查，输出**幻觉清单** |
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

### 四、输出目录结构

```
output/
├── raw/          # 原始语料
├── reports/      # 报告 1.0 / 2.0 / 3.0 / 4.0（.md / .docx）
└── experts/      # 专家意见
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

## 许可证

按项目需要自行选择。
