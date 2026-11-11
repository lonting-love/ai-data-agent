import asyncio
import hmac
import logging
import re
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel, Field

from action_store import claim_action, release_action, session_lock
from config import (
    APP_API_KEY,
    CHART_DIR,
    CHART_URL_PREFIX,
    CHECKPOINT_DB,
    MAX_AUTO_RESUMES,
    MAX_QUERY_CHARS,
    MODEL_API_KEY,
    MODEL_BASE_URL,
    MODEL_NAME,
    SQL_ROW_LIMIT,
    SQL_TIMEOUT_SECONDS,
)
from execute_sql_tool import execute_sql_tool
from observability import get_trace_id, new_trace_id, set_trace_id, trace
from plot_chart_tool import plot_chart_tool
from prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)
CONFIRM_TOOL = "execute_sql_tool"
CHART_PATTERN = re.compile(r"/charts/[A-Za-z0-9_.-]+\.html")

CHART_DIR.mkdir(parents=True, exist_ok=True)

try:
    model = init_chat_model(
        model=MODEL_NAME,
        api_key=MODEL_API_KEY,
        base_url=MODEL_BASE_URL,
        temperature=0.2,
    )
except Exception as exc:  # 缺少密钥时也要能启动，方便健康检查与前端排障
    model = None
    logger.warning("模型初始化失败: %s", exc)


def _cleanup_old_charts(max_age_seconds: int = 24 * 3600) -> None:
    cutoff = time.time() - max_age_seconds
    for path in CHART_DIR.glob("chart_*.html"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    from schema_store import get_vectorstore

    _cleanup_old_charts()
    app.state.vectorstore = get_vectorstore()
    trace("app.schema_backend", backend=app.state.vectorstore.backend_name)
    async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINT_DB)) as checkpointer:
        await checkpointer.setup()
        app.state.checkpointer = checkpointer
        yield


app = FastAPI(title="AI数据分析助手", version="1.1.0", lifespan=lifespan)
app.mount(CHART_URL_PREFIX, StaticFiles(directory=str(CHART_DIR)), name="charts")


@app.middleware("http")
async def trace_middleware(request, call_next):
    set_trace_id(request.headers.get("X-Trace-Id") or new_trace_id())
    response = await call_next(request)
    response.headers["X-Trace-Id"] = get_trace_id()
    return response


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if APP_API_KEY and not hmac.compare_digest(x_api_key or "", APP_API_KEY):
        raise HTTPException(status_code=401, detail="无效的 API Key")


class ChatRequest(BaseModel):
    query: str = Field(default="", max_length=MAX_QUERY_CHARS, description="用户的查询问题")
    session_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="会话ID",
    )
    confirmed: bool = Field(default=False, description="用户是否已确认执行待审批的 SQL")
    cancel: bool = Field(default=False, description="是否取消当前待审批的操作")
    action_id: str = Field(default="", max_length=64, description="前端生成的幂等键")


def _message_text(message: object) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


def _pending_tool_calls(state: object) -> list[dict]:
    messages = state.values.get("messages", [])
    if not messages:
        return []
    return list(getattr(messages[-1], "tool_calls", None) or [])


def _sql_confirmation(tool_calls: list[dict]) -> dict | None:
    sql_statements = []
    for tool_call in tool_calls:
        if tool_call.get("name") != CONFIRM_TOOL:
            continue
        args = tool_call.get("args")
        sql = args.get("sql_query", "") if isinstance(args, dict) else ""
        if isinstance(sql, str) and sql.strip():
            sql_statements.append(sql.strip())

    if not sql_statements:
        return None

    blocks = "\n\n".join(
        "```sql\n" + sql.replace("```", "` ` `") + "\n```" for sql in sql_statements
    )
    return {
        "requires_confirmation": True,
        "response": "即将执行以下 SQL 查询，请确认后继续：\n\n" + blocks,
        "pending_sql": "\n\n".join(sql_statements),
    }


def _charts_in(text: str) -> list[str]:
    return sorted(set(CHART_PATTERN.findall(text or "")))


def _sum_usage(messages: list) -> dict:
    total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for message in messages:
        usage = getattr(message, "usage_metadata", None)
        if not isinstance(usage, dict):
            continue
        for key in total:
            value = usage.get(key)
            if isinstance(value, int):
                total[key] += value
    return total if total["total_tokens"] else {}


async def _stream_until_pause(agent, config: dict, payload: dict | None) -> str:
    """消费 Agent 输出,遇到需要用户确认的 SQL 暂停点或运行结束就返回。"""
    response = ""
    for _ in range(MAX_AUTO_RESUMES):
        async for step in agent.astream(payload, config=config, stream_mode="values"):
            last_message = step["messages"][-1]
            if isinstance(last_message, AIMessage):
                text = _message_text(last_message)
                if text.strip():
                    response = text

        state = await agent.aget_state(config)
        if not state.next:
            return response
        if _sql_confirmation(_pending_tool_calls(state)):
            return response
        # 画图等非 SQL 工具的暂停直接自动放行
        payload = None

    return response


async def _run_turn(agent, config: dict, payload: dict | None) -> tuple[str, dict | None]:
    response = await _stream_until_pause(agent, config, payload)
    state = await agent.aget_state(config)
    return response, _sql_confirmation(_pending_tool_calls(state))


@app.get("/health")
async def health():
    vectorstore = getattr(app.state, "vectorstore", None)
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "model_ready": model is not None,
        "schema_backend": getattr(vectorstore, "backend_name", "unknown"),
        "limits": {"rows": SQL_ROW_LIMIT, "sql_timeout_seconds": SQL_TIMEOUT_SECONDS},
        "auth_enabled": bool(APP_API_KEY),
    }


@app.post("/chat", dependencies=[Depends(require_api_key)])
async def chat_with_agent(request: ChatRequest):
    if request.cancel:
        async with session_lock(request.session_id):
            await app.state.checkpointer.adelete_thread(request.session_id)
        trace("chat.cancel", session_id=request.session_id)
        return {"response": "已取消本次操作。", "requires_confirmation": False, "trace_id": get_trace_id()}

    if model is None:
        raise HTTPException(status_code=503, detail="模型未初始化,请检查 .env 中的 DEEPSEEK_API_KEY")

    if not claim_action(request.session_id, request.action_id):
        trace("chat.duplicate", session_id=request.session_id, action_id=request.action_id)
        return {
            "response": "该操作已提交，请勿重复点击。",
            "requires_confirmation": False,
            "duplicate": True,
            "trace_id": get_trace_id(),
        }

    try:
        async with session_lock(request.session_id):
            result = await _process(request)
        trace(
            "chat.done",
            session_id=request.session_id,
            confirmed=request.confirmed,
            requires_confirmation=result.get("requires_confirmation", False),
        )
        return result
    except HTTPException:
        release_action(request.session_id, request.action_id, completed=False)
        raise
    except Exception:
        release_action(request.session_id, request.action_id, completed=False)
        logger.exception("处理 /chat 请求失败")
        trace("chat.error", session_id=request.session_id)
        raise HTTPException(status_code=500, detail="处理你的问题时出错,请稍后重试。")


async def _process(request: ChatRequest) -> dict:
    question = request.query.strip()
    if not question and not request.confirmed:
        raise HTTPException(status_code=422, detail="请输入问题")

    docs = await asyncio.to_thread(lambda: app.state.vectorstore.similarity_search(question or "确认执行", k=6))
    dynamic_schema = "\n".join(doc.text for doc in docs)
    trace("chat.start", session_id=request.session_id, confirmed=request.confirmed, schema_tables=[doc.table for doc in docs])

    agent = create_agent(
        model,
        tools=[execute_sql_tool, plot_chart_tool],
        system_prompt=SYSTEM_PROMPT.format(dynamic_schema=dynamic_schema),
        checkpointer=app.state.checkpointer,
        interrupt_before=["tools"],
    )
    config = {"configurable": {"thread_id": request.session_id}}
    state = await agent.aget_state(config)

    if request.confirmed:
        if not state.next:
            return {"response": "当前没有等待确认的操作。", "requires_confirmation": False, "trace_id": get_trace_id()}
        response, confirmation = await _run_turn(agent, config, None)
    elif state.next:
        # 已有暂停点：SQL 等待确认；其他工具（画图）自动恢复
        confirmation = _sql_confirmation(_pending_tool_calls(state))
        if confirmation:
            if question:
                raise HTTPException(status_code=409, detail="有 SQL 等待确认，请先确认或取消后再提问。")
            confirmation["trace_id"] = get_trace_id()
            return confirmation
        response, confirmation = await _run_turn(agent, config, None)
        if not confirmation and question:
            response, confirmation = await _run_turn(
                agent,
                config,
                {"messages": [{"role": "user", "content": question}]},
            )
    else:
        response, confirmation = await _run_turn(
            agent,
            config,
            {"messages": [{"role": "user", "content": question}]},
        )

    if confirmation:
        confirmation["trace_id"] = get_trace_id()
        return confirmation

    final_state = await agent.aget_state(config)
    usage = _sum_usage(list(final_state.values.get("messages", [])))
    if usage:
        trace("chat.usage", **usage)
    text = response or "抱歉,没有生成有效回答,请换个问法再试。"
    return {
        "response": text,
        "requires_confirmation": False,
        "charts": _charts_in(text),
        "usage": usage,
        "trace_id": get_trace_id(),
    }
