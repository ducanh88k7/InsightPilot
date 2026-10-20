from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from insightpilot.planning.demo import run_demo


if __name__ == "__main__":
    result = run_demo()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
