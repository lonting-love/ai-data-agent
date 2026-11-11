"""图表工具：输出到 charts/，由 backend 以 /charts 静态目录对外提供。"""

import shutil
import uuid
from pathlib import Path

import pandas as pd
import plotly
import plotly.express as px
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import CHART_DIR, CHART_URL_PREFIX
from observability import trace

MAX_POINTS = 50

CHART_TYPE_ALIASES = {
    "bar": "bar",
    "柱状图": "bar",
    "柱状": "bar",
    "line": "line",
    "折线图": "line",
    "折线": "line",
}


def _ensure_plotly_js() -> bool:
    """把 plotly.min.js 放进 charts/，浏览器离线也能渲染（static 目录会一起托管）。"""
    target = CHART_DIR / "plotly.min.js"
    if target.exists():
        return True
    source = Path(plotly.__file__).resolve().parent / "package_data" / "plotly.min.js"
    if not source.exists():
        return False
    shutil.copyfile(source, target)
    return True


class PlotChartInput(BaseModel):
    x_data: list[str] = Field(description="x轴的数据,例如产品名称、日期")
    y_data: list[float] = Field(description="y轴的数据,例如销售额、营收额")
    chart_type: str = Field(description="图表类型,bar(柱状图)或者line(折线图)")
    title: str = Field(description="图表标题")


@tool("plot_chart_tool", args_schema=PlotChartInput)
def plot_chart_tool(x_data: list[str], y_data: list[float], chart_type: str, title: str) -> str:
    """接受数据并用plotly将其转化成图表保存为HTML文件"""
    if not x_data or not y_data:
        return "没有可绘制的数据"
    if len(x_data) != len(y_data):
        return f"x轴({len(x_data)}项)和y轴({len(y_data)}项)的数据数量不一致"

    x_data = [str(item) for item in x_data]
    y_data = [float(item) for item in y_data]
    if len(x_data) > MAX_POINTS:
        x_data, y_data = x_data[:MAX_POINTS], y_data[:MAX_POINTS]

    chart_type = CHART_TYPE_ALIASES.get(chart_type.strip().lower(), chart_type.strip().lower())
    title = title.strip()[:120] or "数据图表"

    frame = pd.DataFrame({"类别": x_data, "数值": y_data})
    if chart_type == "bar":
        fig = px.bar(frame, x="类别", y="数值", title=title)
    elif chart_type == "line":
        fig = px.line(frame, x="类别", y="数值", title=title, markers=True)
    else:
        return f"不支持的图表类型: {chart_type},只支持 bar 或 line"

    CHART_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"chart_{uuid.uuid4().hex[:8]}.html"
    out_path = CHART_DIR / filename
    use_local_js = _ensure_plotly_js()
    fig.write_html(out_path, include_plotlyjs="directory" if use_local_js else "cdn", full_html=True)

    url = f"{CHART_URL_PREFIX}/{filename}"
    trace("chart.ok", chart=filename, points=len(x_data), chart_type=chart_type)
    return f"图表生成成功! URL: {url} (文件: charts/{filename})"
