"""Create CURRENT synthetic evidence; old snapshots should correctly expire."""

import json
from pathlib import Path

from verifigen.domains.support import demo_bad_draft, demo_source

folder = Path("runs/input")
folder.mkdir(parents=True, exist_ok=True)
source = demo_source()
for name, data in (("source", source), ("candidate", demo_bad_draft(source))):
    (folder / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
print(
    "Created runs/input/source.json and runs/input/candidate.json; evidence expires in 5 minutes."
)
