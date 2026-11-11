"""黄金问题集评测：跑通 /chat 全链路（含 SQL 确认），统计成功率、延迟与 token 成本。

用法：
    python eval/run_eval.py --base http://localhost:8000 --min-success 0.8
"""

import argparse
import json
import statistics
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
QUESTIONS = ROOT / "questions.jsonl"
REPORTS = ROOT / "reports"


def run_case(base: str, case: dict, timeout: float, api_key: str) -> dict:
    headers = {"X-API-Key": api_key} if api_key else {}
    session_id = uuid.uuid4().hex
    started = time.monotonic()
    confirmations = 0
    usage = {"input_tokens": 0, "output_tokens": 0}
    error = ""

    try:
        payload = {"query": case["question"], "session_id": session_id}
        for _ in range(3):
            response = requests.post(f"{base}/chat", json=payload, headers=headers, timeout=timeout)
            if response.status_code != 200:
                error = f"HTTP {response.status_code}: {response.text[:200]}"
                break
            data = response.json()
            for key in usage:
                usage[key] += int(data.get("usage", {}).get(key, 0) or 0)
            if not data.get("requires_confirmation"):
                break
            confirmations += 1
            payload = {
                "query": case["question"],
                "session_id": session_id,
                "confirmed": True,
                "action_id": uuid.uuid4().hex,
            }
        else:
            error = "确认次数过多"
    except Exception as exc:  # noqa: BLE001 - 评测需要记录任何失败
        data = {"response": ""}
        error = str(exc)
    else:
        if response.status_code != 200:
            data = {"response": ""}
    finally:
        latency_ms = round((time.monotonic() - started) * 1000)

    text = data.get("response", "") if isinstance(data, dict) else ""
    failure_markers = ("【SQL执行失败】", "后端处理失败", "请求后端失败")
    ok = not error and bool(text.strip()) and not any(marker in text for marker in failure_markers)
    expect_any = case.get("expect_any") or []
    if ok and expect_any:
        ok = any(word in text for word in expect_any)
    if case.get("needs_chart") and ok:
        ok = "/charts/" in text or bool(data.get("charts"))

    return {
        "id": case["id"],
        "question": case["question"],
        "ok": ok,
        "latency_ms": latency_ms,
        "confirmations": confirmations,
        "usage": usage,
        "error": error,
        "response_preview": text[:200],
    }


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(ratio * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--min-success", type=float, default=0.0)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    args = parser.parse_args()

    cases = [json.loads(line) for line in args.questions.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = [run_case(args.base, case, args.timeout, args.api_key) for case in cases]

    latencies = [item["latency_ms"] for item in results]
    passed = sum(1 for item in results if item["ok"])
    success_rate = passed / len(results) if results else 0.0
    total_usage = {
        key: sum(item["usage"].get(key, 0) for item in results)
        for key in ("input_tokens", "output_tokens")
    }

    for item in results:
        status = "PASS" if item["ok"] else "FAIL"
        print(f"[{status}] {item['id']} {item['question']} ({item['latency_ms']}ms)")
        if not item["ok"]:
            print(f"       {item['error'] or item['response_preview']}")

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "passed": passed,
        "success_rate": round(success_rate, 4),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 1) if latencies else 0,
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
        },
        "usage": total_usage,
        "confirmations": sum(item["confirmations"] for item in results),
        "results": results,
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"成功率 {passed}/{len(results)} = {success_rate:.1%}")
    print(f"延迟 P50 {summary['latency_ms']['p50']}ms / P95 {summary['latency_ms']['p95']}ms")
    print(f"Token 输入 {total_usage['input_tokens']} / 输出 {total_usage['output_tokens']}")
    print(f"报告: {report_path}")

    if success_rate < args.min_success:
        print(f"低于阈值 {args.min_success:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
