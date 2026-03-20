# -*- coding: utf-8 -*-
"""
图表渲染器：将 LLM 生成的图表描述转为 PNG 图片。
使用 Plotly + Kaleido，纯 Python，零外部依赖。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from src.utils.log import log as _log


def render_timeline(events: list[dict], title: str = "", output_path: Path = None) -> Optional[bytes]:
    """
    渲染时间线图。
    events: [{"date": "2026-02-22", "event": "描述", "category": "分类(可选)"}]
    返回 PNG bytes 或保存到 output_path。
    """
    import plotly.express as px
    import pandas as pd

    df = pd.DataFrame(events)
    if "category" not in df.columns:
        df["category"] = "事件"

    fig = px.timeline(
        df, x_start="date", x_end="date",
        y="category", text="event",
        title=title,
        color="category",
    ) if "date" in df.columns else None

    # 降级为散点图时间线
    if fig is None or len(events) < 2:
        fig = px.scatter(
            df, x="date", y=[0] * len(df), text="event",
            title=title,
        )
        fig.update_traces(textposition="top center", marker=dict(size=12))
        fig.update_yaxes(visible=False)

    fig.update_layout(
        template="plotly_white",
        font=dict(family="Microsoft YaHei, sans-serif", size=12),
        showlegend=False,
        height=400,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return _export(fig, output_path)


def render_bar(data: list[dict], x: str, y: str, title: str = "", output_path: Path = None) -> Optional[bytes]:
    """
    渲染柱状图。
    data: [{"name": "X轴", "value": 123}]
    """
    import plotly.express as px
    import pandas as pd

    df = pd.DataFrame(data)
    fig = px.bar(df, x=x, y=y, title=title, text_auto=True)
    fig.update_layout(
        template="plotly_white",
        font=dict(family="Microsoft YaHei, sans-serif", size=12),
        height=400,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return _export(fig, output_path)


def render_pie(data: list[dict], names: str, values: str, title: str = "", output_path: Path = None) -> Optional[bytes]:
    """渲染饼图。"""
    import plotly.express as px
    import pandas as pd

    df = pd.DataFrame(data)
    fig = px.pie(df, names=names, values=values, title=title)
    fig.update_layout(
        template="plotly_white",
        font=dict(family="Microsoft YaHei, sans-serif", size=12),
        height=400,
    )
    return _export(fig, output_path)


def render_relationship(nodes: list[dict], edges: list[dict], title: str = "", output_path: Path = None) -> Optional[bytes]:
    """
    渲染关系图（网络图）。
    nodes: [{"id": "A", "label": "节点A", "group": "分类"}]
    edges: [{"from": "A", "to": "B", "label": "关系"}]
    """
    import plotly.graph_objects as go
    import networkx as nx

    G = nx.DiGraph()
    for n in nodes:
        G.add_node(n["id"], label=n.get("label", n["id"]), group=n.get("group", ""))
    for e in edges:
        G.add_edge(e["from"], e["to"], label=e.get("label", ""))

    pos = nx.spring_layout(G, seed=42, k=2)

    # 边
    edge_traces = []
    for u, v, data in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_traces.append(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode="lines",
            line=dict(width=1.5, color="#888"),
            hoverinfo="none",
        ))

    # 节点
    node_x, node_y, node_text, node_color = [], [], [], []
    groups = list(set(nx.get_node_attributes(G, "group").values()))
    color_map = {g: i for i, g in enumerate(groups)} if groups else {}

    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        label = G.nodes[node].get("label", node)
        node_text.append(label)
        group = G.nodes[node].get("group", "")
        node_color.append(color_map.get(group, 0))

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        text=node_text, textposition="top center",
        marker=dict(size=20, color=node_color, colorscale="portland", line=dict(width=2, color="white")),
        hoverinfo="text",
    )

    fig = go.Figure(data=edge_traces + [node_trace])
    fig.update_layout(
        title=title,
        template="plotly_white",
        font=dict(family="Microsoft YaHei, sans-serif", size=11),
        showlegend=False,
        height=500,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return _export(fig, output_path)


def render_flowchart(steps: list[dict], title: str = "", output_path: Path = None) -> Optional[bytes]:
    """
    渲染流程图（横向）。
    steps: [{"name": "步骤1", "detail": "说明"}, {"name": "步骤2"}, ...]
    """
    import plotly.graph_objects as go

    n = len(steps)
    fig = go.Figure()

    # 箭头连线
    for i in range(n - 1):
        fig.add_annotation(
            x=i + 0.4, y=0, ax=i + 0.6, ay=0,
            xref="x", yref="y", axref="x", ayref="y",
            arrowhead=3, arrowsize=1.5, arrowwidth=2, arrowcolor="#666",
        )

    # 方框
    for i, step in enumerate(steps):
        fig.add_shape(
            type="rect", x0=i - 0.35, x1=i + 0.35, y0=-0.2, y1=0.2,
            fillcolor="#4ECDC4" if i == 0 else ("#FF6B6B" if i == n - 1 else "#45B7D1"),
            line=dict(width=0), opacity=0.9,
        )
        fig.add_annotation(
            x=i, y=0, text=f"<b>{step['name']}</b>",
            showarrow=False, font=dict(color="white", size=11),
        )
        if step.get("detail"):
            fig.add_annotation(
                x=i, y=-0.35, text=step["detail"],
                showarrow=False, font=dict(size=9, color="#666"),
            )

    fig.update_layout(
        title=title,
        template="plotly_white",
        font=dict(family="Microsoft YaHei, sans-serif"),
        xaxis=dict(visible=False, range=[-0.5, n - 0.5]),
        yaxis=dict(visible=False, range=[-0.6, 0.5]),
        height=250,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return _export(fig, output_path)


def _export(fig, output_path: Path = None) -> Optional[bytes]:
    """导出 Plotly figure 为 PNG bytes。"""
    try:
        png_bytes = fig.to_image(format="png", width=900, height=None, scale=2)
        if output_path:
            output_path = Path(output_path)
            output_path.write_bytes(png_bytes)
            _log(f"  图表已保存: {output_path.name}")
        return png_bytes
    except Exception as e:
        _log(f"  图表导出失败: {e}")
        return None


def render_chart_from_json(chart_json: str, output_path: Path = None) -> Optional[bytes]:
    """
    通用入口：从 LLM 生成的 JSON 描述渲染图表。

    JSON 格式：
    {
        "type": "timeline|bar|pie|relationship|flowchart",
        "title": "图表标题",
        "data": [...],  // 类型相关的数据
        ...类型特有参数
    }
    """
    try:
        spec = json.loads(chart_json)
    except (json.JSONDecodeError, Exception):
        return None

    chart_type = spec.get("type", "")
    title = spec.get("title", "")
    data = spec.get("data", [])

    if chart_type == "timeline":
        return render_timeline(data, title, output_path)
    elif chart_type == "bar":
        return render_bar(data, spec.get("x", "name"), spec.get("y", "value"), title, output_path)
    elif chart_type == "pie":
        return render_pie(data, spec.get("names", "name"), spec.get("values", "value"), title, output_path)
    elif chart_type == "relationship":
        return render_relationship(spec.get("nodes", []), spec.get("edges", []), title, output_path)
    elif chart_type == "flowchart":
        return render_flowchart(data, title, output_path)
    else:
        _log(f"  未知图表类型: {chart_type}")
        return None
