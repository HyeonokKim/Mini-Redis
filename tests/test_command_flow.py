import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mini_redis.bootstrap import build_command_manager

class CommandFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.appendonly_path = base / "appendonly.aof"
        self.snapshot_path = base / "dump.rdb.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build_manager(self):
        return build_command_manager(
            appendonly_path=self.appendonly_path,
            snapshot_path=self.snapshot_path,
        )

    def test_basic_command_flow(self) -> None:
        manager = self.build_manager()
        self.assertIsNotNone(manager.recovery_report)
        self.assertFalse(manager.recovery_report.snapshot_loaded)
        self.assertEqual(manager.recovery_report.replayed_entries, 0)

        self.assertEqual(manager.execute({"name": "PING", "args": []}), "PONG")
        self.assertEqual(manager.execute({"name": "SET", "args": ["user:1", "hello"]}), "OK")
        self.assertEqual(manager.execute({"name": "EXISTS", "args": ["user:1"]}), 1)
        self.assertEqual(manager.execute({"name": "GET", "args": ["user:1"]}), "hello")
        self.assertEqual(manager.execute({"name": "DELETE", "args": ["user:1"]}), 1)
        self.assertEqual(manager.execute({"name": "EXISTS", "args": ["user:1"]}), 0)
        self.assertIsNone(manager.execute({"name": "GET", "args": ["user:1"]}))

    def test_ttl_commands(self) -> None:
        manager = self.build_manager()

        self.assertEqual(manager.execute({"name": "SET", "args": ["temp", "1"]}), "OK")
        self.assertEqual(manager.execute({"name": "EXPIRE", "args": ["temp", "1"]}), 1)
        ttl = manager.execute({"name": "TTL", "args": ["temp"]})
        self.assertIn(ttl, {0, 1})
        time.sleep(1.1)
        self.assertIsNone(manager.execute({"name": "GET", "args": ["temp"]}))
        self.assertEqual(manager.execute({"name": "TTL", "args": ["temp"]}), -2)

    def test_keys_returns_sorted_live_keys(self) -> None:
        manager = self.build_manager()

        manager.execute({"name": "SET", "args": ["b", "2"]})
        manager.execute({"name": "SET", "args": ["a", "1"]})

        self.assertEqual(manager.execute({"name": "KEYS", "args": []}), ["a", "b"])

    def test_incr_and_mget(self) -> None:
        manager = self.build_manager()

        self.assertEqual(manager.execute({"name": "INCR", "args": ["counter"]}), 1)
        self.assertEqual(manager.execute({"name": "INCR", "args": ["counter"]}), 2)
        manager.execute({"name": "SET", "args": ["x", "10"]})

        self.assertEqual(
            manager.execute({"name": "MGET", "args": ["counter", "x", "missing"]}),
            ["2", "10", None],
        )

    def test_save_and_flushdb(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["persist:key", "value"]})

        snapshot_path = Path(manager.execute({"name": "SAVE", "args": []}))
        self.assertEqual(snapshot_path, self.snapshot_path)
        self.assertTrue(snapshot_path.exists())
        self.assertEqual(manager.execute({"name": "FLUSHDB", "args": []}), 1)
        self.assertEqual(manager.execute({"name": "KEYS", "args": []}), [])
        self.assertTrue(self.appendonly_path.exists())

    def test_restore_replays_only_aof_entries_after_snapshot(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["count", "5"]})
        manager.execute({"name": "SAVE", "args": []})
        manager.execute({"name": "INCR", "args": ["count"]})
        manager.execute({"name": "SET", "args": ["name", "mini-redis"]})

        restored = self.build_manager()
        self.assertTrue(restored.recovery_report.snapshot_loaded)
        self.assertEqual(restored.recovery_report.replayed_entries, 2)
        self.assertEqual(restored.execute({"name": "GET", "args": ["count"]}), "6")
        self.assertEqual(
            restored.execute({"name": "GET", "args": ["name"]}),
            "mini-redis",
        )

    def test_restore_replays_expire_after_snapshot(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["session", "ok"]})
        manager.execute({"name": "SAVE", "args": []})
        manager.execute({"name": "EXPIRE", "args": ["session", "1"]})

        restored = self.build_manager()
        ttl = restored.execute({"name": "TTL", "args": ["session"]})
        self.assertIn(ttl, {0, 1})

    def test_rewrite_aof_compacts_current_state(self) -> None:
        manager = self.build_manager()
        manager.execute({"name": "SET", "args": ["name", "redis"]})
        manager.execute({"name": "INCR", "args": ["counter"]})
        manager.execute({"name": "EXPIRE", "args": ["name", "30"]})

        rewritten_path = Path(manager.execute({"name": "REWRITEAOF", "args": []}))
        self.assertEqual(rewritten_path, self.appendonly_path)
        lines = rewritten_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(any('"op": "SET"' in line for line in lines))


if __name__ == "__main__":
    unittest.main()
