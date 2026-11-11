import os
import re
import uuid

import requests
import streamlit as st

BACKEND_BASE = os.getenv("BACKEND_BASE", "http://localhost:8000").rstrip("/")
BACKEND_URL = os.getenv("BACKEND_URL", f"{BACKEND_BASE}/chat")
HEALTH_URL = f"{BACKEND_BASE}/health"
CHART_PATTERN = re.compile(r"/charts/[A-Za-z0-9_.-]+\.html")

st.set_page_config(page_title="AI数据分析助手", page_icon="🤖", layout="wide")
st.title("AI数据分析助手")

for key, default in (
    ("messages", []),
    ("session_id", uuid.uuid4().hex),
    ("pending", None),
    ("api_key", ""),
    ("health", None),
):
    if key not in st.session_state:
        st.session_state[key] = default


def headers() -> dict:
    return {"X-API-Key": st.session_state.api_key} if st.session_state.api_key else {}


def call_backend(payload: dict) -> dict:
    try:
        response = requests.post(BACKEND_URL, json=payload, headers=headers(), timeout=180)
        if response.status_code != 200:
            try:
                detail = response.json().get("detail", "")
            except ValueError:
                detail = ""
            if response.status_code == 401:
                return {"response": "API Key 不正确，请在左侧填写后再试。"}
            return {"response": f"后端处理失败（{response.status_code}）：{detail or '请稍后重试'}"}
        data = response.json()
        if not isinstance(data, dict):
            return {"response": "后端返回格式异常，请稍后重试。"}
        if not isinstance(data.get("response"), str) or not data["response"].strip():
            data["response"] = "后端没有返回有效内容，请稍后重试。"
        return data
    except Exception as exc:
        return {"response": f"请求后端失败：{exc}"}


def extract_charts(data: dict) -> list[str]:
    charts = data.get("charts")
    if isinstance(charts, list) and charts:
        return [url for url in charts if isinstance(url, str)]
    return sorted(set(CHART_PATTERN.findall(data.get("response", ""))))


def add_assistant_message(data: dict) -> None:
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": data["response"],
            "charts": extract_charts(data),
        }
    )


def check_health() -> dict:
    try:
        response = requests.get(HEALTH_URL, timeout=3)
        return response.json() if response.status_code == 200 else {"status": f"HTTP {response.status_code}"}
    except Exception as exc:
        return {"status": f"不可达: {exc}"}


with st.sidebar:
    st.subheader("服务状态")
    if st.button("检查后端"):
        st.session_state.health = check_health()
    if st.session_state.health is None:
        st.session_state.health = check_health()
    health = st.session_state.health or {}
    if health.get("status") == "ok":
        st.success(f"在线 · 模型 {'就绪' if health.get('model_ready') else '未就绪'}")
        st.caption(f"Schema 检索: {health.get('schema_backend')} · 行上限 {health.get('limits', {}).get('rows')}")
    else:
        st.error(f"离线 · {health.get('status', '未知')}")

    st.subheader("访问设置")
    st.session_state.api_key = st.text_input("API Key（后端开启鉴权时填写）", type="password")
    if st.button("清空对话"):
        try:
            requests.post(
                BACKEND_URL,
                json={"session_id": st.session_state.session_id, "cancel": True},
                headers=headers(),
                timeout=10,
            )
        except Exception:
            pass
        st.session_state.messages = []
        st.session_state.pending = None
        st.session_state.session_id = uuid.uuid4().hex
        st.rerun()


def render_chart(url: str) -> None:
    st.components.v1.iframe(f"{BACKEND_BASE}{url}", height=430, scrolling=True)


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        for chart_url in message.get("charts", []):
            render_chart(chart_url)

if st.session_state.pending:
    st.info("SQL 已生成，等待你确认后执行。")
    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button("确认执行", type="primary"):
        pending = st.session_state.pending
        with st.spinner("Agent 正在执行 SQL 并整理结果..."):
            data = call_backend(
                {
                    "query": pending["query"],
                    "session_id": st.session_state.session_id,
                    "confirmed": True,
                    "action_id": uuid.uuid4().hex,
                }
            )
        st.session_state.pending = None
        add_assistant_message(data)
        if data.get("requires_confirmation"):
            st.session_state.pending = {"sql": data.get("pending_sql", ""), "query": pending["query"]}
        st.rerun()

    if cancel_col.button("取消"):
        pending = st.session_state.pending
        call_backend(
            {
                "query": pending["query"],
                "session_id": st.session_state.session_id,
                "cancel": True,
                "action_id": uuid.uuid4().hex,
            }
        )
        st.session_state.messages = []
        st.session_state.pending = None
        st.session_state.session_id = uuid.uuid4().hex
        st.rerun()
else:
    with st.form(key="chat_form", clear_on_submit=True):
        user_input = st.text_input("请输入您的问题：")
        submit_button = st.form_submit_button("发送")

    if submit_button and user_input.strip():
        st.session_state.messages.append({"role": "user", "content": user_input, "charts": []})
        with st.spinner("Agent 正在查数据、画图中..."):
            data = call_backend(
                {
                    "query": user_input,
                    "session_id": st.session_state.session_id,
                }
            )
        add_assistant_message(data)
        if data.get("requires_confirmation"):
            st.session_state.pending = {"sql": data.get("pending_sql", ""), "query": user_input}
        st.rerun()
