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
        self._last_recovery_report = RecoveryReport(
            snapshot_loaded=False,
            replayed_entries=0,
            recovered_keys=0,
            aof_corruption_detected=False,
            ignored_aof_entries=0,
            corrupted_aof_line=None,
        )

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

        report = RecoveryReport(
            snapshot_loaded=snapshot_loaded,
            replayed_entries=replayed_entries,
            recovered_keys=redis.key_count(),
            aof_corruption_detected=aof_result.corruption_detected,
            ignored_aof_entries=aof_result.ignored_entries,
            corrupted_aof_line=aof_result.corrupted_line,
        )
        self._last_recovery_report = report
        return report

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

    def info(self) -> dict[str, Any]:
        aof_path = self._aof_writer._path
        snapshot_path = self._snapshot_store._path
        return {
            "aof_path": str(aof_path),
            "aof_exists": aof_path.exists(),
            "aof_size": aof_path.stat().st_size if aof_path.exists() else 0,
            "snapshot_path": str(snapshot_path),
            "snapshot_exists": snapshot_path.exists(),
            "snapshot_size": snapshot_path.stat().st_size if snapshot_path.exists() else 0,
            "operation_log_length": len(self._operation_log),
            "last_recovery": {
                "snapshot_loaded": self._last_recovery_report.snapshot_loaded,
                "replayed_entries": self._last_recovery_report.replayed_entries,
                "recovered_keys": self._last_recovery_report.recovered_keys,
                "aof_corruption_detected": self._last_recovery_report.aof_corruption_detected,
                "ignored_aof_entries": self._last_recovery_report.ignored_aof_entries,
                "corrupted_aof_line": self._last_recovery_report.corrupted_aof_line,
            },
        }

    @property
    def operation_log(self) -> list[tuple[object, ...]]:
        return list(self._operation_log)

    @property
    def last_recovery_report(self) -> RecoveryReport:
        return self._last_recovery_report
