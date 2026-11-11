"""结构化 JSONL 链路日志：每条事件带 trace_id，便于串联一次请求内的模型/工具调用。"""

import json
import threading
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from config import LOG_DIR

_current_trace: ContextVar[str] = ContextVar("trace_id", default="")
_write_lock = threading.Lock()


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_trace_id(trace_id: str) -> None:
    _current_trace.set(trace_id)


def get_trace_id() -> str:
    return _current_trace.get() or "-"


MAX_LOG_BYTES = 5 * 1024 * 1024


def trace(event: str, **fields) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "trace_id": get_trace_id(),
        "event": event,
    }
    record.update(fields)
    line = json.dumps(record, ensure_ascii=False, default=str)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / "trace.jsonl"
        with _write_lock:
            if log_file.exists() and log_file.stat().st_size > MAX_LOG_BYTES:
                log_file.replace(LOG_DIR / "trace.jsonl.1")
            with open(log_file, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except OSError:
        pass
