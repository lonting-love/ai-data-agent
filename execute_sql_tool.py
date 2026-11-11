"""只读 SQL 工具：文件只读打开 + SQLite authorizer + 超时中断 + 行数硬上限。"""

import sqlite3
import time

from langchain_core.tools import tool

from config import DB_PATH, SQL_ROW_LIMIT, SQL_TIMEOUT_SECONDS
from observability import trace

MAX_RESULT_CHARS = 200_000
MAX_VALUE_BYTES = 1_000_000

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
    sqlite3.SQLITE_TRANSACTION,
    sqlite3.SQLITE_SAVEPOINT,
}

_BLOCKED_FUNCTIONS = {
    "load_extension",
    "readfile",
    "writefile",
    "randomblob",
    "zeroblob",
    "printf",
    "hex",
    "quote",
}


def _strip_comments(sql: str) -> str:
    out: list[str] = []
    i, size = 0, len(sql)
    closing: str | None = None
    while i < size:
        ch = sql[i]
        if closing:
            out.append(ch)
            if ch == closing:
                if i + 1 < size and sql[i + 1] == closing:
                    out.append(sql[i + 1])
                    i += 2
                    continue
                closing = None
            i += 1
            continue
        if ch in ("'", '"', "`", "["):
            closing = "]" if ch == "[" else ch
            out.append(ch)
            i += 1
            continue
        if ch == "-" and i + 1 < size and sql[i + 1] == "-":
            while i < size and sql[i] != "\n":
                i += 1
            out.append(" ")
            continue
        if ch == "/" and i + 1 < size and sql[i + 1] == "*":
            i += 2
            while i + 1 < size and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _has_multiple_statements(sql: str) -> bool:
    closing: str | None = None
    for index, ch in enumerate(sql):
        if closing:
            if ch == closing:
                closing = None
            continue
        if ch in ("'", '"', "`", "["):
            closing = "]" if ch == "[" else ch
            continue
        if ch == ";" and sql[index + 1:].strip():
            return True
    return False


def _authorizer(action, arg1, arg2, dbname, trigger) -> int:
    if action not in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_READ and dbname not in ("main", "temp", None):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and str(arg2 or "").lower() in _BLOCKED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _run_query(query: str) -> tuple[list[str], list[tuple], bool]:
    deadline = time.monotonic() + SQL_TIMEOUT_SECONDS

    def progress() -> int:
        return 1 if time.monotonic() > deadline else 0

    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, timeout=2)
    try:
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_VALUE_BYTES)
        conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 50_000)
        conn.set_authorizer(_authorizer)
        conn.set_progress_handler(progress, 10000)
        wrapped = f"SELECT * FROM (\n{query}\n) LIMIT {SQL_ROW_LIMIT + 1}"
        cursor = conn.execute(wrapped)
        columns = [item[0] for item in cursor.description or []]
        rows = cursor.fetchmany(SQL_ROW_LIMIT + 1)
        truncated = len(rows) > SQL_ROW_LIMIT
        return columns, rows[:SQL_ROW_LIMIT], truncated
    finally:
        conn.close()


@tool("execute_sql_tool")
def execute_sql_tool(sql_query: str) -> str:
    """连接本地 SQLite 数据库,执行只读 SELECT 查询"""
    started = time.monotonic()
    if not DB_PATH.exists():
        trace("sql.error", reason="db_missing", path=str(DB_PATH))
        return "数据库文件不存在,请先运行 generate_sample_data.py 生成数据"

    query = _strip_comments(sql_query).strip().rstrip(";").strip()
    lowered = query.lower()

    if not lowered.startswith(("select", "with")):
        trace("sql.reject", reason="not_select", sql=sql_query[:300])
        return "只允许执行 SELECT 查询及 WITH 语句"
    if _has_multiple_statements(query):
        trace("sql.reject", reason="multi_statement", sql=query[:300])
        return "一次只能执行一条 SQL 语句"

    try:
        columns, rows, truncated = _run_query(query)
    except sqlite3.DatabaseError as exc:
        message = str(exc)
        if "interrupted" in message.lower():
            message = f"查询超过 {SQL_TIMEOUT_SECONDS:g} 秒被中断,请缩小范围(加 WHERE/LIMIT)"
        elif "not authorized" in message.lower():
            message = "语句包含只读模式下不允许的操作"
        trace("sql.error", duration_ms=round((time.monotonic() - started) * 1000), error=message, sql=query[:300])
        return f"【SQL执行失败】{message}。请检查SQL语句,修正后重新调用工具。"
    except Exception as exc:  # noqa: BLE001 - 错误要回传给模型自我修正
        trace("sql.error", duration_ms=round((time.monotonic() - started) * 1000), error=str(exc), sql=query[:300])
        return f"【SQL执行失败】{exc}。请检查SQL语句,修正后重新调用工具。"

    duration_ms = round((time.monotonic() - started) * 1000)
    trace("sql.ok", duration_ms=duration_ms, rows=len(rows), truncated=truncated, sql=query[:300])

    if not rows:
        return "查询成功但结果为空"

    lines = [" | ".join(columns)]
    total_chars = len(lines[0])
    for row in rows:
        line = " | ".join("NULL" if value is None else str(value) for value in row)
        total_chars += len(line) + 1
        if total_chars > MAX_RESULT_CHARS:
            lines.append(f"...(结果过大,已截断到约 {MAX_RESULT_CHARS // 1000}K 字符)")
            return "\n".join(lines)
        lines.append(line)
    if truncated:
        lines.append(f"...(结果超过 {SQL_ROW_LIMIT} 行,仅显示前 {SQL_ROW_LIMIT} 行)")
    return "\n".join(lines)
