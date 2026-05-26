from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from commitr import cache


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._original_dir = cache.CACHE_DIR
        cache.CACHE_DIR = Path(self.tmp.name)

    def tearDown(self) -> None:
        cache.CACHE_DIR = self._original_dir
        self.tmp.cleanup()

    def test_store_then_lookup_returns_message(self) -> None:
        cache.store(diff="diff a", model="m1", message="feat: add a")

        hit = cache.lookup(diff="diff a", model="m1")

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.message, "feat: add a")
        self.assertEqual(hit.model, "m1")

    def test_lookup_miss_for_different_diff(self) -> None:
        cache.store(diff="diff a", model="m1", message="feat: a")

        self.assertIsNone(cache.lookup(diff="diff b", model="m1"))

    def test_lookup_miss_for_different_model(self) -> None:
        cache.store(diff="diff a", model="m1", message="feat: a")

        self.assertIsNone(cache.lookup(diff="diff a", model="m2"))

    def test_style_signature_changes_invalidate_cache(self) -> None:
        cache.store(diff="d", model="m", message="x", style_signature="sig-1")

        self.assertIsNone(cache.lookup(diff="d", model="m", style_signature="sig-2"))

    def test_ttl_expiry_drops_entry(self) -> None:
        path = cache.store(diff="d", model="m", message="x")
        assert path is not None

        # Backdate the entry past the TTL.
        data = json.loads(path.read_text())
        data["created_at"] = time.time() - 100
        path.write_text(json.dumps(data))

        self.assertIsNone(cache.lookup(diff="d", model="m", ttl_seconds=50))
        self.assertFalse(path.exists())  # auto-cleaned

    def test_clear_removes_all_entries(self) -> None:
        cache.store(diff="d1", model="m", message="x1")
        cache.store(diff="d2", model="m", message="x2")

        removed = cache.clear()

        self.assertGreaterEqual(removed, 2)
        self.assertEqual(cache.stats()["entries"], 0)

    def test_store_skips_when_inputs_missing(self) -> None:
        self.assertIsNone(cache.store(diff="", model="m", message="x"))
        self.assertIsNone(cache.store(diff="d", model="", message="x"))
        self.assertIsNone(cache.store(diff="d", model="m", message=""))


if __name__ == "__main__":
    unittest.main()
