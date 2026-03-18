"""Append-only file support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AOFWriter:
    """Write operation events to an append-only log."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, operation: str, args: list[object]) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"op": operation, "args": args}) + "\n")

    def read_entries(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []

        entries: list[dict[str, Any]] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                entries.append(json.loads(text))
        return entries

    def rewrite(self, entries: list[dict[str, Any]]) -> Path:
        with self._path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")
        return self._path
