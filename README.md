# chatgpt-document

从 AI 对话记录（ChatGPT、Gemini、Perplexity）抓取或导入内容，经 Kimi 大模型分类整理、生成深度报告，支持报告 1.0 → 专家评审 → 报告 2.0 → 报告 3.0 最终版。

## 环境要求

- Python 3.8+
- Kimi（月之暗面）API Key：[Moonshot 开放平台](https://platform.moonshot.cn) 创建

## 安装

```bash
cd D:\BaiduSyncdisk\aicoding\chatgpt-document
pip install -r requirements.txt
```

首次使用 Pyppeteer 时会自动下载 Chromium，请保持网络畅通。

## 配置

复制 `.env.example` 为 `.env`，填入 Kimi API Key：

```
KIMI_API_KEY=你的API_Key
KIMI_MODEL=kimi-k2-turbo-preview
```

或在系统环境变量中设置 `KIMI_API_KEY`。

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

### 二、各步骤详解

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

### 三、输出目录结构

```
output/
├── raw/          # 原始语料
├── reports/      # 报告 1.0 / 2.0 / 3.0（.md / .docx）
└── experts/      # 专家意见
```

---

## 使用方式

### 一键全流程

```bash
# 从分享链接或本地文件
python main.py all "分享链接或本地文件路径" -o 输出名 -s A

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
