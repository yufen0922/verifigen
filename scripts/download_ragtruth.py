"""Download pinned official Git blobs and verify their full SHA-256 digests."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

from verifigen.ragtruth import FILE_HASHES

BLOBS = {
    "response.jsonl": "f9ae5913fb9976684f3e13be3cd3465062db54cc",
    "source_info.jsonl": "119277774009f110aa58596b93f9512f62594a89",
}
HASHES = {"response.jsonl": FILE_HASHES["responses"], "source_info.jsonl": FILE_HASHES["sources"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/ragtruth-official"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, blob in BLOBS.items():
        target = args.output / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == HASHES[name]:
            print(f"Verified cached {name}")
            continue
        request = Request(
            f"https://api.github.com/repos/ParticleMedia/RAGTruth/git/blobs/{blob}",
            headers={
                "User-Agent": "VerifiGen-dataset-builder",
            },
        )
        for attempt in range(3):
            try:
                with urlopen(request, timeout=60) as response:
                    body = json.load(response)
                content = base64.b64decode(body["content"], validate=False)
                if hashlib.sha256(content).hexdigest() != HASHES[name]:
                    raise ValueError(f"Checksum mismatch: {name}")
                target.write_bytes(content)
                print(f"Downloaded and verified {name}")
                break
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(2**attempt)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        raise SystemExit(
            f"Download failed: {exc}. GitHub may rate-limit unauthenticated requests. Retry later or provide the official raw files to build_ragtruth_eval.py; the checked-in cohort needs no download."
        ) from None
