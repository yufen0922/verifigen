"""Measure threshold sensitivity using only frozen development sample IDs."""

import argparse
import hashlib
import json
from pathlib import Path

from verifigen.calibration import threshold_curve
from verifigen.ragtruth import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument(
        "--samples", type=Path, default=Path("benchmarks/data/ragtruth-600/samples.jsonl")
    )
    args = parser.parse_args()
    try:
        config = json.loads((args.results / "config.json").read_text())
        if config["split"] != "dev":
            raise ValueError("Cannot select thresholds on evaluation records")
        if config["samples_sha256"] != hashlib.sha256(args.samples.read_bytes()).hexdigest():
            raise ValueError("Frozen source dataset hash differs")
        records = read_jsonl(args.results / "records.jsonl")
        if len(records) != len(config["selected_case_ids"]) or {r["id"] for r in records} != set(
            config["selected_case_ids"]
        ):
            raise ValueError("Development run is incomplete or has unexpected IDs")
        report = {"config": config, **threshold_curve(records, read_jsonl(args.samples))}
        (args.results / "thresholds.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k != "config"}, indent=2))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"Calibration failed: {exc}\n")


if __name__ == "__main__":
    main()
