"""Export blind review materials or reconcile externally completed human annotations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from verifigen.comparison import blind_packets
from verifigen.human_review import HumanAnnotation, annotation_template, reconcile, score_outputs
from verifigen.ragtruth import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument(
        "--samples", type=Path, default=Path("benchmarks/data/ragtruth-600/samples.jsonl")
    )
    export.add_argument("--records", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    merge = sub.add_parser("reconcile")
    merge.add_argument("--packets", type=Path, required=True)
    merge.add_argument("--annotations", type=Path, nargs="+", required=True)
    merge.add_argument("--adjudications", type=Path)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--records", type=Path)
    merge.add_argument("--mapping", type=Path)
    merge.add_argument(
        "--samples", type=Path, default=Path("benchmarks/data/ragtruth-600/samples.jsonl")
    )
    args = parser.parse_args()
    try:
        if args.command == "export":
            if args.output.exists() and any(args.output.iterdir()):
                raise ValueError("Export to a new empty directory")
            records = read_jsonl(args.records)
            for row in records:
                row.setdefault("arm", "quality_loop")
            packets, mapping = blind_packets(read_jsonl(args.samples), records)
            args.output.mkdir(parents=True, exist_ok=True)
            for name, rows in (
                ("packets.jsonl", packets),
                ("private-mapping.jsonl", mapping),
                ("reviewer-a-template.jsonl", annotation_template(packets, "reviewer-a")),
                ("reviewer-b-template.jsonl", annotation_template(packets, "reviewer-b")),
            ):
                (args.output / name).write_text(
                    "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8",
                )
            (args.output / "annotation-schema.json").write_text(
                json.dumps(HumanAnnotation.model_json_schema(), indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Exported {len(packets)} anonymous packets; templates are unfilled, not labels.")
        else:
            result = reconcile(
                read_jsonl(args.packets),
                [r for path in args.annotations for r in read_jsonl(path)],
                read_jsonl(args.adjudications) if args.adjudications else [],
            )
            if bool(args.records) != bool(args.mapping):
                raise ValueError(
                    "Supply both --records and --mapping to compute human effect rates"
                )
            if args.records:
                result["output_metrics"] = score_outputs(
                    read_jsonl(args.records),
                    read_jsonl(args.mapping),
                    result,
                    read_jsonl(args.samples),
                )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
            print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"Human review failed: {exc}\n")


if __name__ == "__main__":
    main()
