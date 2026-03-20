# 图表生成规范

在以下场景必须插入图表（用 ```chart-json 代码块，JSON 格式）：

## 1. 时间线：涉及 3+ 个有时间顺序的事件

```chart-json
{
  "type": "timeline",
  "title": "事件时间线标题",
  "data": [
    {"date": "2026-01-01", "event": "事件描述1"},
    {"date": "2026-02-15", "event": "事件描述2"},
    {"date": "2026-03-20", "event": "事件描述3"}
  ]
}
```

## 2. 柱状图：涉及数据对比

```chart-json
{
  "type": "bar",
  "title": "对比标题",
  "x": "name",
  "y": "value",
  "data": [
    {"name": "类别A", "value": 120},
    {"name": "类别B", "value": 85}
  ]
}
```

## 3. 关系图：涉及 3+ 个利益相关方或实体关系

```chart-json
{
  "type": "relationship",
  "title": "关系图标题",
  "nodes": [
    {"id": "A", "label": "实体A", "group": "分类1"},
    {"id": "B", "label": "实体B", "group": "分类2"}
  ],
  "edges": [
    {"from": "A", "to": "B", "label": "关系描述"}
  ]
}
```

## 4. 流程图：涉及因果链、政策传导、决策路径

```chart-json
{
  "type": "flowchart",
  "title": "流程图标题",
  "data": [
    {"name": "步骤1", "detail": "说明"},
    {"name": "步骤2", "detail": "说明"},
    {"name": "步骤3", "detail": "说明"}
  ]
}
```

## 5. 饼图：涉及占比分布

```chart-json
{
  "type": "pie",
  "title": "饼图标题",
  "names": "name",
  "values": "value",
  "data": [
    {"name": "类别A", "value": 60},
    {"name": "类别B", "value": 40}
  ]
}
```

## 规则
- 每章至少 1 个 chart-json 图表或结构化表格
- 图表标题用中文
- JSON 必须合法，字段名用英文
- 如果内容更适合表格呈现，用 Markdown 表格替代图表
- 不要同时用图表和表格呈现相同数据
