# chatgpt-document

从 AI 对话记录（ChatGPT、Gemini、Perplexity）抓取或导入内容，经 Kimi 大模型分类整理、生成深度报告，支持报告 2.0（专家评审）与报告 3.0（按章节分段、篇幅充足）。

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

## 流程概览

| 步骤 | 说明 |
|------|------|
| **Step1** | 用 Pyppeteer 打开分享链接，回溯到对话开头，逐条抓取内容保存为本地 txt；若内容 < 1000 字节则等待 15 秒重试 |
| **Step2** | 调用 Kimi API：对本地内容生成标题、摘要、关键词，并生成 4~7 章的「深度调查报告 1.0」 |
| **Step3** | 调用 Kimi 生成 3 位评审专家：事实与逻辑 / 结构与深度 / 可行性与合规，输出专家意见文档 |
| **Step4** | 根据专家意见修订报告，生成「深度报告 2.0」，并导出 Word（标题层级字号与粗体、段落与列表、对比表格） |

## 支持的数据源

| 平台 | 方式 | 说明 |
|------|------|------|
| ChatGPT | 分享链接 | `chatgpt.com/share/xxx` |
| Gemini | 分享链接 | `g.co/gemini/share` 或 `gemini.google.com` |
| Perplexity | 分享链接 | `perplexity.ai` |
| 任意 | 本地文件 | `.txt` / `.json` / `.md`（导出或复制粘贴） |

## 使用方式

### 一键全流程（URL 或文件）

```bash
# 从分享链接
python main.py all-v3 "https://chatgpt.com/share/xxx" -o 项目名

# 从本地文件（Gemini/Perplexity 导出等）
python main.py all-v3 output/raw/xxx.txt -o 项目名
```

### 分步执行

```bash
# 方式1：抓取分享链接（ChatGPT/Gemini/Perplexity）
python main.py crawl "https://chatgpt.com/share/xxx" -o my_share

# 方式2：导入本地文件
python main.py import my_export.json -o my_share

# 方式3：统一入口（自动识别 URL 或文件）
python main.py fetch "https://chatgpt.com/share/xxx" -o my_share

# Step2：生成报告 1.0
python main.py report-v1 output/raw/my_share.txt -o my_share

# Step3：三位专家评审
python main.py experts output/reports/my_share_report_v1.md -o my_share

# Step4：报告 2.0 + Word
python main.py report-v2 output/reports/my_share_report_v1.md -o my_share
```

也可直接运行各模块：

```bash
python -m src.step1_crawler "https://chatgpt.com/share/xxx" -o my_share
python -m src.step2_report_v1 output/raw/my_share.txt -o my_share
python -m src.step3_experts output/reports/my_share_report_v1.md -o my_share
python -m src.step4_report_v2 output/reports/my_share_report_v1.md -o my_share
```

## 输出目录结构

```
output/
  raw/              # Step1 抓取的原始对话文本
  reports/          # 报告 1.0/2.0 的 .md、.docx，以及 meta JSON
  experts/          # 三位专家意见及汇总
```

## 注意事项

- **ChatGPT 分享页**：若页面结构更新，可能需在 `src/step1_crawler.py` 中调整选择器。
- **内容不足重试**：若多次重试后仍不足 1000 字节，程序仍会保存当前内容并给出警告。
- **Kimi 模型**：默认 `kimi-k2-turbo-preview`，可在 `.env` 中改为 `kimi-latest` 等。
- **长文本**：Step2/Step4 会对过长内容做截断，以保证在模型上下文限制内。

## 许可证

按项目需要自行选择。
