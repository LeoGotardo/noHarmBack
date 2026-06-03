import pytest
import tempfile
import os
from security.persistentHashTable import PersistentHashTable


@pytest.fixture
def table(tmp_path):
    return PersistentHashTable(str(tmp_path / "test.jsonl"))


class TestPersistentHashTable:
    def test_set_and_get(self, table):
        table.set("key1", "value1")
        assert table.get("key1") == "value1"

    def test_get_missing_returns_none(self, table):
        assert table.get("ghost") is None

    def test_exists_true(self, table):
        table.set("k", "v")
        assert table.exists("k") is True

    def test_exists_false(self, table):
        assert table.exists("ghost") is False

    def test_delete_removes_key(self, table):
        table.set("k", "v")
        table.delete("k")
        assert table.exists("k") is False

    def test_delete_nonexistent_noop(self, table):
        table.delete("ghost")  # should not raise

    def test_overwrite(self, table):
        table.set("k", "v1")
        table.set("k", "v2")
        assert table.get("k") == "v2"

    def test_persistence_across_instances(self, tmp_path):
        path = str(tmp_path / "persist.jsonl")
        t1 = PersistentHashTable(path)
        t1.set("foo", "bar")
        t1.set("baz", "qux")

        t2 = PersistentHashTable(path)
        assert t2.get("foo") == "bar"
        assert t2.get("baz") == "qux"

    def test_delete_persists_across_instances(self, tmp_path):
        path = str(tmp_path / "del.jsonl")
        t1 = PersistentHashTable(path)
        t1.set("k", "v")
        t1.delete("k")

        t2 = PersistentHashTable(path)
        assert t2.exists("k") is False

    def test_cleanup_removes_expired(self, table):
        table.set("expired", "old")
        table.set("valid", "new")
        table.cleanup(isExpired=lambda v: v == "old")
        assert table.exists("expired") is False
        assert table.exists("valid") is True

    def test_cleanup_compacts_file(self, tmp_path):
        path = str(tmp_path / "compact.jsonl")
        t = PersistentHashTable(path)
        for i in range(10):
            t.set(f"k{i}", "val")
        t.cleanup(isExpired=lambda v: False)  # keep all — rewrites file
        lines = open(path).readlines()
        assert len(lines) == 10  # compacted from append-only to 10 lines

    def test_creates_directories(self, tmp_path):
        nested = str(tmp_path / "a" / "b" / "c" / "table.jsonl")
        t = PersistentHashTable(nested)
        t.set("k", "v")
        assert os.path.exists(nested)

    def test_corrupted_lines_ignored(self, tmp_path):
        path = str(tmp_path / "corrupt.jsonl")
        with open(path, "w") as f:
            f.write('{"key":"valid","value":"ok","op":"add"}\n')
            f.write("NOT JSON\n")
            f.write("\n")
        t = PersistentHashTable(path)
        assert t.get("valid") == "ok"
