from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def percentile(values: list[int], ratio: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * ratio))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    attempts = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    latest = {
        (row["case_id"], row["system"], row["turn"]): row
        for row in attempts
    }
    rows = list(latest.values())
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["system"]].append(row)

    lines = ["# Báo cáo paired evaluation", ""]
    lines.append("## Chỉ số tự động")
    lines.append("")
    lines.append("| System | Lượt | HTTP 200 | Degraded | Mean ms | Median ms | P95 ms | Provider calls |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for system in ("old", "new"):
        items = groups.get(system, [])
        healthy_times = [item["wall_ms"] for item in items if item["http_status"] == 200]
        calls = sum(item.get("provider_call_count") or 0 for item in items)
        lines.append(
            f"| {system} | {len(items)} | {sum(item['http_status'] == 200 for item in items)} | "
            f"{sum(bool(item.get('degraded')) for item in items)} | "
            f"{round(statistics.mean(healthy_times), 1) if healthy_times else '-'} | "
            f"{round(statistics.median(healthy_times), 1) if healthy_times else '-'} | "
            f"{percentile(healthy_times, .95) or '-'} | {calls} |"
        )

    violations = []
    for row in groups.get("new", []):
        if row["http_status"] != 200:
            continue
        expected_calls = 0 if row.get("blocked_category") else 1
        if row.get("provider_call_count") != expected_calls:
            violations.append(row)
    lines.extend(
        [
            "",
            f"- Vi phạm hợp đồng precheck=0 call, accepted=1 call: **{len(violations)}**.",
            f"- Phân bố category: `{dict(Counter(row['category'] for row in rows))}`.",
            "",
            "## Phiếu chấm thủ công",
            "",
            "Chấm mỗi tiêu chí 0–2: đúng dữ kiện, đủ/đúng trọng tâm, bám nguồn, đúng vai, rõ ràng, an toàn/memory.",
            "",
            "| Case | Turn | Old | New | Winner | Ghi chú |",
            "|---|---:|---|---|---|---|",
        ]
    )
    keys = sorted({(row["case_id"], row["turn"]) for row in rows})
    by_key = {(row["case_id"], row["turn"], row["system"]): row for row in rows}
    for case_id, turn in keys:
        old = by_key.get((case_id, turn, "old"), {})
        new = by_key.get((case_id, turn, "new"), {})
        old_answer = str(old.get("answer") or old.get("error") or "-").replace("|", "\\|")[:180]
        new_answer = str(new.get("answer") or new.get("error") or "-").replace("|", "\\|")[:180]
        lines.append(f"| {case_id} | {turn} | {old_answer} | {new_answer} | TODO | TODO |")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
