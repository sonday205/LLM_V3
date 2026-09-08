from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "source_manifest.yaml"
OUTPUT_DIR = ROOT / ".runtime" / "crawl"
USER_AGENT = "HistoricalRagResearchBot/1.0 (educational corpus curation)"


def allowed_by_robots(client: httpx.Client, url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    try:
        response = client.get(robots_url)
        parser.parse(response.text.splitlines() if response.is_success else [])
        return parser.can_fetch(USER_AGENT, url)
    except httpx.HTTPError:
        return False


def crawl(delay_seconds: float) -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, object]] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client:
        for item in manifest.get("sources", []):
            url = item["url"]
            if not allowed_by_robots(client, url):
                print(f"SKIP robots: {url}")
                continue
            response = client.get(url)
            response.raise_for_status()
            extracted = trafilatura.extract(response.text, include_links=False, include_comments=False) or ""
            digest = hashlib.sha256(response.content).hexdigest()
            target = OUTPUT_DIR / f"{item['character_id']}-{digest[:12]}.txt"
            target.write_text(extracted, encoding="utf-8")
            index.append(
                {
                    **item,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "sha256": digest,
                    "local_file": target.name,
                    "status": response.status_code,
                }
            )
            print(f"FETCH {response.status_code}: {url}")
            time.sleep(delay_seconds)
    (OUTPUT_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tải nguồn công khai để biên tập corpus; không tự ingest.")
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    args = parser.parse_args()
    crawl(args.delay_seconds)


if __name__ == "__main__":
    main()
