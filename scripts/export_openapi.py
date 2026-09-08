from __future__ import annotations

from pathlib import Path

import yaml

from app.main import app


OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "openapi.yaml"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        yaml.safe_dump(app.openapi(), allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
