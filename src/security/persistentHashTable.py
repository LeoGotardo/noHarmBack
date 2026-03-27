import json
import os

from typing import Any


class PersistentHashTable:
    """
    Hash table with disk persistence using an append-only log (JSONL).

    Each write operation appends a new line to the file instead of
    rewriting the entire file — O(1) cost per operation.

    On initialization, the current state is reconstructed by replaying
    all events in order. The cleanup method compacts the file by
    removing expired entries.

    File format (.jsonl):
        {"key": "<hash>", "value": "<iso_datetime>", "op": "add"}
        {"key": "<hash>", "value": "<iso_datetime>", "op": "remove"}
    """

    def __init__(self, filepath: str):
        self._filepath = filepath
        self._table: dict[str, Any] = {}

        self._ensureFile()
        self._load()


    # ── Public interface ───────────────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        """Adds or updates an entry and persists the event."""
        self._table[key] = value
        self._appendEvent(key, value, "add")


    def get(self, key: str) -> Any | None:
        """Returns the value associated with the key, or None if it does not exist."""
        return self._table.get(key)


    def exists(self, key: str) -> bool:
        """Checks whether the key exists in the table."""
        return key in self._table


    def delete(self, key: str) -> None:
        """Removes an entry and persists the removal event."""
        if key in self._table:
            del self._table[key]
            self._appendEvent(key, None, "remove")


    def cleanup(self, isExpired: callable) -> None:
        """
        Removes expired entries from memory and compacts the file.

        Args:
            isExpired: A callable that receives a value and returns True if expired.
                       Example: lambda exp: datetime.fromisoformat(exp) < datetime.utcnow()
        """
        self._table = {
            key: value
            for key, value in self._table.items()
            if not isExpired(value)
        }

        self._rewrite()


    # ── Persistence ───────────────────────────────────────────────────────────

    def _ensureFile(self) -> None:
        """Creates the file and any required directories if they do not exist."""
        dirPath = os.path.dirname(self._filepath)

        if dirPath:
            os.makedirs(dirPath, exist_ok=True)

        if not os.path.exists(self._filepath):
            open(self._filepath, 'w').close()


    def _load(self) -> None:
        """
        Reconstructs the current state by replaying all events from the file in order.
        'add' events insert entries; 'remove' events delete them.
        Corrupted lines are silently ignored.
        """
        with open(self._filepath, 'r') as file:
            for line in file:
                line = line.strip()

                if not line:
                    continue

                try:
                    event = json.loads(line)
                    op    = event.get("op")
                    key   = event.get("key")
                    value = event.get("value")

                    if op == "add" and key:
                        self._table[key] = value

                    elif op == "remove" and key:
                        self._table.pop(key, None)

                except (json.JSONDecodeError, KeyError):
                    continue


    def _appendEvent(self, key: str, value: Any, op: str) -> None:
        """
        Appends a single event to the end of the file — O(1).
        Never rewrites the entire file.
        """
        event = json.dumps({
            "key":   key,
            "value": value,
            "op":    op
        })

        with open(self._filepath, 'a') as file:
            file.write(event + '\n')


    def _rewrite(self) -> None:
        """
        Rewrites the file with only the current clean state.
        Called exclusively by cleanup — O(n), but infrequent.
        """
        with open(self._filepath, 'w') as file:
            for key, value in self._table.items():
                event = json.dumps({
                    "key":   key,
                    "value": value,
                    "op":    "add"
                })
                file.write(event + '\n')