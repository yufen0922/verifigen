"""Build the pinned 600-response public cohort from official JSONL files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from verifigen.ragtruth import materialize


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/data/ragtruth-600"))
    args = parser.parse_args()
    try:
        print(json.dumps(materialize(args.responses, args.sources, args.output), indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Dataset preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
