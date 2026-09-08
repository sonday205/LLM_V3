from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "evaluation" / "quality_50.yaml"
BASELINE_TIMEOUT_FLOOR_MS = 3500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paired live evaluation: baseline vs one-call RAG.")
    parser.add_argument("--old-url", default="http://127.0.0.1:8005")
    parser.add_argument("--new-url", default="http://127.0.0.1:8010")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "results" / "paired.jsonl")
    parser.add_argument("--delay-seconds", type=float, default=10.0)
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def load_completed(path: Path) -> set[tuple[str, str, int]]:
    if not path.exists():
        return set()
    completed = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            provider_failed = (
                item.get("degraded")
                and item.get("provider") is None
                and item.get("wall_ms", 0) < BASELINE_TIMEOUT_FLOOR_MS
            )
            if item.get("http_status") == 200 and not provider_failed:
                completed.add((item["case_id"], item["system"], item["turn"]))
    return completed


def append_result(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")


def observed_old_calls(body: dict[str, Any]) -> int:
    timings = (body.get("debug") or {}).get("timings_ms") or {}
    return int("router_provider" in timings) + int("answer_provider" in timings)


def quota_or_provider_unavailable(result: dict[str, Any]) -> bool:
    """Nhận diện cả lỗi HTTP lẫn fallback HTTP 200 của bản baseline."""
    if result["http_status"] in {401, 403, 429, 503}:
        return True
    provider_fallback = bool(
        result.get("degraded")
        and result.get("provider") is None
        and result.get("answer")
    )
    # Baseline hiện tại có timeout 4 giây. Fallback sát mốc này là một kết quả
    # latency/degraded cần ghi nhận; quota/credential failure thường trả nhanh.
    return provider_fallback and result.get("wall_ms", 0) < BASELINE_TIMEOUT_FLOOR_MS


async def call(
    client: httpx.AsyncClient,
    base_url: str,
    system: str,
    case: dict[str, Any],
    turn: int,
    message: str,
    api_key: str | None,
) -> dict[str, Any]:
    headers = {"X-API-Key": api_key} if system == "new" and api_key else {}
    started = time.perf_counter()
    try:
        response = await client.post(
            f"{base_url}/v1/characters/{case['character_id']}/chat",
            headers=headers,
            json={
                "session_id": f"eval-{case['id'].lower()}-{system}",
                "message": message,
                "debug": True,
            },
        )
        wall_ms = int((time.perf_counter() - started) * 1000)
        try:
            body = response.json()
        except ValueError:
            body = {"detail": response.text[:500]}
        debug = body.get("debug") or {}
        return {
            "created_at": datetime.now(UTC).isoformat(),
            "case_id": case["id"],
            "category": case["category"],
            "character_id": case["character_id"],
            "system": system,
            "turn": turn,
            "question": message,
            "http_status": response.status_code,
            "wall_ms": wall_ms,
            "answer": body.get("answer"),
            "degraded": body.get("degraded"),
            "provider": body.get("provider") or debug.get("provider"),
            "model": body.get("model") or debug.get("model"),
            "provider_call_count": (
                body.get("provider_call_count") if system == "new" else observed_old_calls(body)
            ),
            "blocked_category": body.get("blocked_category"),
            "memory_used": body.get("memory_used", debug.get("memory_used")),
            "sources": body.get("sources"),
            "timings_ms": body.get("timings_ms") or debug.get("timings_ms"),
            "error": body.get("detail") if response.status_code >= 400 else None,
        }
    except httpx.HTTPError as exc:
        return {
            "created_at": datetime.now(UTC).isoformat(),
            "case_id": case["id"],
            "category": case["category"],
            "character_id": case["character_id"],
            "system": system,
            "turn": turn,
            "question": message,
            "http_status": 0,
            "wall_ms": int((time.perf_counter() - started) * 1000),
            "answer": None,
            "provider_call_count": None,
            "error": type(exc).__name__,
        }


async def run(args: argparse.Namespace) -> None:
    cases = (yaml.safe_load(args.cases.read_text(encoding="utf-8")) or {})["cases"]
    if args.limit:
        cases = cases[: args.limit]
    completed = load_completed(args.output)
    api_key = next((item.strip() for item in os.getenv("APP_API_KEYS", "").split(",") if item.strip()), None)
    total_turns = sum(len(case.get("messages", [case.get("message")])) for case in cases) * 2
    current = len(completed)
    async with httpx.AsyncClient(timeout=45) as client:
        for case_index, case in enumerate(cases):
            systems = (("old", args.old_url), ("new", args.new_url))
            if case_index % 2:
                systems = tuple(reversed(systems))
            messages = case.get("messages") or [case["message"]]
            for system, base_url in systems:
                for turn, message in enumerate(messages, 1):
                    key = (case["id"], system, turn)
                    if key in completed:
                        continue
                    result = await call(client, base_url, system, case, turn, message, api_key)
                    append_result(args.output, result)
                    current += 1
                    print(
                        f"[{current}/{total_turns}] {case['id']} {system} turn={turn} "
                        f"HTTP={result['http_status']} wall={result['wall_ms']}ms calls={result.get('provider_call_count')}"
                    )
                    if quota_or_provider_unavailable(result):
                        print(
                            "Dừng an toàn khi provider/quota không sẵn sàng; "
                            "chạy lại sẽ resume từ checkpoint."
                        )
                        return
                    if current < total_turns:
                        await asyncio.sleep(args.delay_seconds)


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
