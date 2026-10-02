"""rotate-encryption-key against real rows written through the API."""
from sqlalchemy import Text, select, type_coerce

from conftest import _engine
from core.config import config
from helpers import register, open_chat

NEW_KEY = "rotated-database-encryption-key-xyz"


def _seed(client):
    a, b = register(client), register(client)
    chatId = open_chat(client, a, b)  # befriends them too
    client.post("/messages", json={"chatId": chatId, "content": "hello there"}, headers=a["headers"])
    client.post("/posts", json={"content": "a post", "visibility": "community"}, headers=a["headers"])
    return a


def _allValues():
    from jobs.rotateEncryptionKey import encryptedColumns
    with _engine.connect() as conn:
        for table, columns in encryptedColumns().items():
            for row in conn.execute(select(*[type_coerce(c, Text) for c in columns])).all():
                yield from (v for v in row if v is not None)


def test_rotation_moves_every_value_to_the_new_key_and_is_resumable(client):
    from jobs.rotateEncryptionKey import _decrypts, _engine as aes, rotate
    _seed(client)
    before = list(_allValues())
    assert before, "the seed should have written encrypted values"

    with _engine.connect() as conn:
        first = rotate(conn, config.DATABASE_ENCRYPTION_KEY, NEW_KEY)
    assert first["rewritten"] == len(before)
    assert first["undecryptable"] == 0

    old, new = aes(config.DATABASE_ENCRYPTION_KEY), aes(NEW_KEY)
    after = list(_allValues())
    assert all(_decrypts(new, v) for v in after)
    assert not any(_decrypts(old, v) for v in after)

    # A second run — as after a crash halfway — finds nothing left to do.
    with _engine.connect() as conn:
        second = rotate(conn, config.DATABASE_ENCRYPTION_KEY, NEW_KEY)
    assert second["rewritten"] == 0
    assert second["already"] == len(after)


def test_plaintext_survives_the_rotation(client):
    from jobs.rotateEncryptionKey import _engine as aes, rotate
    _seed(client)
    old = aes(config.DATABASE_ENCRYPTION_KEY)
    plaintextBefore = sorted(old.decrypt(v) for v in _allValues())

    with _engine.connect() as conn:
        rotate(conn, config.DATABASE_ENCRYPTION_KEY, NEW_KEY)

    new = aes(NEW_KEY)
    assert sorted(new.decrypt(v) for v in _allValues()) == plaintextBefore


def test_a_value_under_a_third_key_fails_the_table_and_writes_nothing(client):
    from jobs.rotateEncryptionKey import _engine as aes, rotate
    from sqlalchemy import text
    a = _seed(client)
    stranger = aes("some-third-key").encrypt("x")
    with _engine.connect() as conn:
        conn.execute(text("UPDATE tb_0 SET cl_0d = :v WHERE cl_0a = :id"), {"v": stranger, "id": a["uid"]})
        conn.commit()
        result = rotate(conn, config.DATABASE_ENCRYPTION_KEY, NEW_KEY)
    assert result["undecryptable"] == 1

    # tb_0 was left exactly as it was: still under the old key.
    old = aes(config.DATABASE_ENCRYPTION_KEY)
    with _engine.connect() as conn:
        usernames = conn.execute(text("SELECT cl_0b FROM tb_0")).scalars().all()
    from jobs.rotateEncryptionKey import _decrypts
    assert all(_decrypts(old, u) for u in usernames)


def test_dry_run_writes_nothing(client):
    from jobs.rotateEncryptionKey import rotate
    _seed(client)
    before = sorted(_allValues())
    with _engine.connect() as conn:
        result = rotate(conn, config.DATABASE_ENCRYPTION_KEY, NEW_KEY, dryRun=True)
    assert result["rewritten"] == len(before)
    assert sorted(_allValues()) == before
