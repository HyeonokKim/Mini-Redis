"""Persistence hooks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from mini_redis.persistence.aof import AOFReadResult
from mini_redis.persistence.aof import AOFWriter
from mini_redis.persistence.rdb import RDBSnapshotStore

if TYPE_CHECKING:
    from mini_redis.engine.redis import Redis


@dataclass(frozen=True)
class RecoveryReport:
    snapshot_loaded: bool
    replayed_entries: int
    recovered_keys: int
    aof_corruption_detected: bool
    ignored_aof_entries: int
    corrupted_aof_line: int | None


class PersistenceManager:
    """Coordinate append-only logging and snapshots."""

    def __init__(self, aof_writer: AOFWriter, snapshot_store: RDBSnapshotStore) -> None:
        self._operation_log: list[tuple[object, ...]] = []
        self._aof_writer = aof_writer
        self._snapshot_store = snapshot_store

    def append(self, operation: str, *args: object) -> None:
        self._operation_log.append((operation, *args))
        self._aof_writer.append(operation, list(args))

    def save_snapshot(self, payload: dict[str, Any]) -> Path:
        return self._snapshot_store.save(payload)

    def restore(self, redis: "Redis") -> RecoveryReport:
        redis.reset_state()
        self._operation_log = []
        snapshot = self._snapshot_store.load()
        aof_offset = 0
        snapshot_loaded = snapshot is not None
        if snapshot is not None:
            redis.restore_snapshot(snapshot)
            self._operation_log = [
                tuple(entry) for entry in snapshot.get("operation_log", [])
            ]
            aof_offset = int(snapshot.get("aof_offset", len(self._operation_log)))

        aof_result = self._aof_writer.read_entries()
        replayed_entries = 0
        for entry in aof_result.entries[aof_offset:]:
            operation = str(entry["op"])
            args = list(entry.get("args", []))
            redis.replay_operation(operation, args)
            self._operation_log.append((operation, *args))
            replayed_entries += 1

        return RecoveryReport(
            snapshot_loaded=snapshot_loaded,
            replayed_entries=replayed_entries,
            recovered_keys=redis.key_count(),
            aof_corruption_detected=aof_result.corruption_detected,
            ignored_aof_entries=aof_result.ignored_entries,
            corrupted_aof_line=aof_result.corrupted_line,
        )

    def load_snapshot(self, redis: "Redis") -> bool:
        snapshot = self._snapshot_store.load()
        if snapshot is None:
            return False

        redis.reset_state()
        redis.restore_snapshot(snapshot)
        self._operation_log = [
            tuple(entry) for entry in snapshot.get("operation_log", [])
        ]
        return True

    def rewrite_aof(self, state_entries: list[dict[str, Any]]) -> Path:
        return self._aof_writer.rewrite(state_entries)

    @property
    def operation_log(self) -> list[tuple[object, ...]]:
        return list(self._operation_log)
