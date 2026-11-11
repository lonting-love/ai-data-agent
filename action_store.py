"""会话级互斥 + 确认动作幂等，防止重复点击导致同一 SQL 被执行两次。"""

import asyncio
import time

_MAX_SESSIONS = 512
_COMPLETED_TTL = 300.0

_locks: dict[str, asyncio.Lock] = {}
_claims: dict[str, float] = {}


def session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _locks:
        if len(_locks) >= _MAX_SESSIONS:
            # 只回收未持有的锁，避免驱逐正在执行的会话
            idle = next((key for key, lock in _locks.items() if not lock.locked()), None)
            if idle is not None:
                _locks.pop(idle, None)
        _locks[session_id] = asyncio.Lock()
    return _locks[session_id]


def _prune() -> None:
    now = time.monotonic()
    expired = [key for key, done_at in _claims.items() if now - done_at > _COMPLETED_TTL]
    for key in expired:
        _claims.pop(key, None)


def claim_action(session_id: str, action_id: str) -> bool:
    """首次提交返回 True；重复提交（进行中或刚完成）返回 False。"""
    if not action_id:
        return True
    _prune()
    key = f"{session_id}:{action_id}"
    if key in _claims:
        return False
    _claims[key] = time.monotonic()
    return True


def release_action(session_id: str, action_id: str, completed: bool = True) -> None:
    if not action_id:
        return
    key = f"{session_id}:{action_id}"
    if completed:
        _claims[key] = time.monotonic()
    else:
        _claims.pop(key, None)
