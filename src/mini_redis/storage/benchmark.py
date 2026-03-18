"""Independent storage benchmark helpers for Redis and MongoDB backends."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from mini_redis.storage.manager import StorageManager
from mini_redis.storage.mongo_manager import MongoManager


@dataclass(frozen=True)
class BenchmarkResult:
    """Simple benchmark summary that callers can print or assert on."""

    target: str
    operation: str
    operations: int
    elapsed_seconds: float
    ops_per_second: float


class StorageBenchmarkSuite:
    """Run Redis-memory and MongoDB benchmarks without coupling the two paths."""

    def benchmark_redis_set(
        self,
        storage: StorageManager,
        operations: int,
        *,
        key_prefix: str = "redis:bench:",
    ) -> BenchmarkResult:
        started_at = perf_counter()
        for index in range(operations):
            storage.set(f"{key_prefix}{index}", str(index))
        elapsed = perf_counter() - started_at
        return self._result("redis", "set", operations, elapsed)

    def benchmark_mongo_write(
        self,
        mongo: MongoManager,
        operations: int,
        *,
        key_prefix: str = "mongo:bench:",
    ) -> BenchmarkResult:
        started_at = perf_counter()
        for index in range(operations):
            mongo.write_value(f"{key_prefix}{index}", str(index))
        elapsed = perf_counter() - started_at
        return self._result("mongo", "write", operations, elapsed)

    def benchmark_mongo_delete(
        self,
        mongo: MongoManager,
        operations: int,
        *,
        key_prefix: str = "mongo:bench:",
    ) -> BenchmarkResult:
        started_at = perf_counter()
        for index in range(operations):
            mongo.delete_key(f"{key_prefix}{index}")
        elapsed = perf_counter() - started_at
        return self._result("mongo", "delete", operations, elapsed)

    def _result(
        self,
        target: str,
        operation: str,
        operations: int,
        elapsed_seconds: float,
    ) -> BenchmarkResult:
        ops_per_second = 0.0 if elapsed_seconds == 0 else operations / elapsed_seconds
        return BenchmarkResult(
            target=target,
            operation=operation,
            operations=operations,
            elapsed_seconds=elapsed_seconds,
            ops_per_second=ops_per_second,
        )
