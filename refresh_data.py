from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.pipeline import run_pipeline


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Refresh MARA mNAV dashboard data.")
    parser.add_argument("--days", type=int, default=None, help="How many days of history to fetch.")
    parser.add_argument("--output", type=Path, default=None, help="Optional output JSON path.")
    args = parser.parse_args()

    result = run_pipeline(days=args.days, output_path=args.output)
    print(f"Saved {result.row_count} rows to {result.output_path} at {result.generated_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
