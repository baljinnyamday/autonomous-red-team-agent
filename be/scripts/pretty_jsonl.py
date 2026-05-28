#!/usr/bin/env python3
"""Pretty-print a JSONL file for human reading (one expanded object per record)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def pretty_jsonl(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        blocks.append(json.dumps(json.loads(stripped), indent=2, ensure_ascii=False))
    path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} <file.jsonl>")
    pretty_jsonl(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
