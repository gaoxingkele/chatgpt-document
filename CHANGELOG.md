# 更新日志

## [Unreleased]

## [0.6.0] - 2025-02-12

### 新增

- **Step6 报告 4.0**：对报告 3.0 做事实核查与出处标注
  - 新增 `report-v4` 命令，按章节提交 Perplexity API 分析并标注引用
  - 支持 `.md` 和 `.docx` 输入格式
  - 在正文插入 `[n]` 引用标记，文末生成 References 列表
  - 调用次数 = 章节数，引用编码按章节顺序递增

- **Perplexity 引用接口**：`llm_client.perplexity_chat_with_citations()` 返回 content 与 citations

### 修改

- Perplexity 模型默认值由 `llama-3.1-sonar-small-128k-online` 更新为 `sonar`（旧模型已废弃）
- Perplexity API 错误时输出详细响应内容便于排查
