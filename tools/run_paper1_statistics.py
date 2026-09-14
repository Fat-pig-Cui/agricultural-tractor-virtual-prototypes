"""Write the paper-1 20-seed summary without invoking legacy paper-2 protocols."""
from __future__ import annotations

import json
from pathlib import Path

from run_statistics import lift_statistics


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    output = ROOT / "results" / "paper1_statistics_20seeds.json"
    output.write_text(
        json.dumps(lift_statistics(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
