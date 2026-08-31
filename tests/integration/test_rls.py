"""Row Level Security, tested at the database rather than through the API.

The other `TestXxxRLS` classes in this suite drive the API and would pass with
the policies dropped — what they check is that the *services* scope their
queries. These tests bypass the services entirely and talk to the tables, so a
failure here means the policies themselves are wrong or absent.

They need a role that does not bypass RLS. The default TEST_DATABASE_URL user
is usually the one that created the database, and on a stock Postgres image
that is a superuser — for whom policies do not exist. `rls_session` skips the
module rather than passing vacuously when that is the case.
"""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import Session

from infrastructure.database.rlsContext import RLSContext


RLS_DATABASE_URL = os.getenv("RLS_TEST_DATABASE_URL", os.getenv("TEST_DATABASE_URL", ""))

USER_A = f"rls-a-{uuid.uuid4()}"
USER_B = f"rls-b-{uuid.uuid4()}"


@pytest.fixture(scope="module")
def rls_engine():
    engine = create_engine(RLS_DATABASE_URL)

    with engine.connect() as connection:
        bypasses = connection.execute(
            text(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
        ).scalar()

        if bypasses:
            pytest.skip(
                "This role bypasses RLS, so the policies cannot be observed. "
                "Point RLS_TEST_DATABASE_URL at a NOSUPERUSER/NOBYPASSRLS role."
            )

        hasPolicies = connection.execute(
            text("SELECT count(*) FROM pg_policies WHERE tablename = 'tb_1'")
        ).scalar()

        if not hasPolicies:
            pytest.fail("migration 20260831_02 has not been applied to the test database")

    yield engine
    engine.dispose()


@pytest.fixture
def seeded(rls_engine):
    """Two users, each with a streak, plus a chat between them and one message.

    Written with no RLS context, which the policies read as "no user" and let
    through — the same escape the auth routes and the push fan-out rely on.
    """
    chatId = uuid.uuid4()

    with Session(rls_engine) as session:
        for userId in (USER_A, USER_B):
            session.execute(
                text(
                    "INSERT INTO tb_0 (cl_0a, cl_0b, cl_0b_h, cl_0c, cl_0c_h, cl_0e,"
                    "                  created_at, updated_at)"
                    " VALUES (:id, 'x', :h1, 'y', :h2, 1, now(), now())"
                ),
                {"id": userId, "h1": f"{userId}-u", "h2": f"{userId}-e"},
            )
            session.execute(
                text(
                    "INSERT INTO tb_1 (cl_1a, cl_1b, cl_1c, cl_1e, cl_1f, created_at, updated_at)"
                    " VALUES (:id, :owner, 'enc', 1, false, now(), now())"
                ),
                {"id": uuid.uuid4(), "owner": userId},
            )

        session.execute(
            text(
                "INSERT INTO tb_3 (cl_3a, cl_3b, cl_3c, cl_3d, cl_3f, created_at, updated_at)"
                " VALUES (:id, :a, :b, 'enc', 1, now(), now())"
            ),
            {"id": chatId, "a": USER_A, "b": USER_B},
        )
        session.execute(
            text(
                "INSERT INTO tb_4 (cl_4a, cl_4b, cl_4c, cl_4d, cl_4e, cl_4f, created_at, updated_at)"
                " VALUES (:id, :chat, :sender, 'enc', 7, 'enc', now(), now())"
            ),
            {"id": uuid.uuid4(), "chat": chatId, "sender": USER_A},
        )
        session.commit()

    yield chatId

    with Session(rls_engine) as session:
        session.execute(text("DELETE FROM tb_4 WHERE cl_4b = :chat"), {"chat": chatId})
        session.execute(text("DELETE FROM tb_3 WHERE cl_3a = :chat"), {"chat": chatId})
        session.execute(
            text("DELETE FROM tb_1 WHERE cl_1b = ANY(:ids)"), {"ids": [USER_A, USER_B]}
        )
        session.execute(
            text("DELETE FROM tb_0 WHERE cl_0a = ANY(:ids)"), {"ids": [USER_A, USER_B]}
        )
        session.commit()


def _asUser(engine, userId):
    session = Session(engine)
    RLSContext.setUserId(session, userId)
    return session


class TestStreakIsolation:
    def test_a_sees_only_their_own_streak(self, rls_engine, seeded):
        with _asUser(rls_engine, USER_A) as session:
            owners = session.execute(text("SELECT cl_1b FROM tb_1")).scalars().all()

        assert owners == [USER_A]

    def test_no_context_sees_both(self, rls_engine, seeded):
        """The escape the push fan-out and the auth routes depend on."""
        with Session(rls_engine) as session:
            owners = set(session.execute(text("SELECT cl_1b FROM tb_1")).scalars().all())

        assert {USER_A, USER_B} <= owners

    def test_a_cannot_write_a_streak_for_b(self, rls_engine, seeded):
        from sqlalchemy.exc import ProgrammingError

        with _asUser(rls_engine, USER_A) as session:
            with pytest.raises(ProgrammingError) as raised:
                session.execute(
                    text(
                        "INSERT INTO tb_1 (cl_1a, cl_1b, cl_1c, cl_1e, cl_1f, created_at, updated_at)"
                        " VALUES (:id, :owner, 'enc', 1, false, now(), now())"
                    ),
                    {"id": uuid.uuid4(), "owner": USER_B},
                )
                session.flush()

        assert "row-level security" in str(raised.value).lower()

    def test_a_cannot_update_b_streak(self, rls_engine, seeded):
        """Silent, not an error: the row is invisible, so the UPDATE matches nothing."""
        with _asUser(rls_engine, USER_A) as session:
            result = session.execute(
                text("UPDATE tb_1 SET cl_1f = true WHERE cl_1b = :owner"),
                {"owner": USER_B},
            )
            session.commit()

        assert result.rowcount == 0


class TestUserVisibility:
    def test_users_stay_readable_across_accounts(self, rls_engine, seeded):
        """Friend search matches an exact username; it has to see other rows."""
        with _asUser(rls_engine, USER_A) as session:
            found = session.execute(
                text("SELECT cl_0a FROM tb_0 WHERE cl_0a = :id"), {"id": USER_B}
            ).scalar()

        assert found == USER_B

    def test_a_cannot_update_b_profile(self, rls_engine, seeded):
        with _asUser(rls_engine, USER_A) as session:
            result = session.execute(
                text("UPDATE tb_0 SET cl_0e = 9 WHERE cl_0a = :id"), {"id": USER_B}
            )
            session.commit()

        assert result.rowcount == 0


class TestMessageScope:
    def test_participant_reads_the_message(self, rls_engine, seeded):
        with _asUser(rls_engine, USER_B) as session:
            count = session.execute(
                text("SELECT count(*) FROM tb_4 WHERE cl_4b = :chat"), {"chat": seeded}
            ).scalar()

        assert count == 1

    def test_outsider_reads_nothing(self, rls_engine, seeded):
        with _asUser(rls_engine, f"rls-outsider-{uuid.uuid4()}") as session:
            count = session.execute(
                text("SELECT count(*) FROM tb_4 WHERE cl_4b = :chat"), {"chat": seeded}
            ).scalar()

        assert count == 0

    def test_recipient_may_mark_the_senders_message_read(self, rls_engine, seeded):
        """Scoped through the chat, not the sender — this is why."""
        with _asUser(rls_engine, USER_B) as session:
            result = session.execute(
                text("UPDATE tb_4 SET cl_4e = 8 WHERE cl_4b = :chat"), {"chat": seeded}
            )
            session.commit()

        assert result.rowcount == 1


class TestContextLifetime:
    def test_context_survives_a_commit(self, rls_engine, seeded):
        """Repositories commit mid-request; the context has to outlive that.

        With a transaction-local setting this returns 2 — the context is gone
        after the commit, every policy falls back to its no-context escape, and
        RLS quietly stops applying for the rest of the request.
        """
        with _asUser(rls_engine, USER_A) as session:
            session.execute(text("SELECT 1"))
            session.commit()

            owners = session.execute(text("SELECT cl_1b FROM tb_1")).scalars().all()

        assert owners == [USER_A]

    def test_context_does_not_leak_to_the_next_checkout(self, rls_engine, seeded):
        """A pooled connection must not carry its user to whoever gets it next."""
        with _asUser(rls_engine, USER_A) as session:
            session.execute(text("SELECT cl_1b FROM tb_1")).scalars().all()
            # No clear, no rollback: the request simply ends.

        with Session(rls_engine) as session:
            owners = set(session.execute(text("SELECT cl_1b FROM tb_1")).scalars().all())

        assert {USER_A, USER_B} <= owners

    def test_a_reused_connection_carries_no_context(self, seeded):
        """The pool is the leak path, so pin it to one connection and check.

        `pool_size=1, max_overflow=0` guarantees the second session gets the
        same physical connection the first one used. It must still start with
        no context: the variable is transaction-local, so it cannot outlive the
        transaction that set it, and `after_begin` stamps the empty string for a
        session that has no user.
        """
        pinned = create_engine(
            RLS_DATABASE_URL, poolclass=QueuePool, pool_size=1, max_overflow=0
        )
        try:
            with _asUser(pinned, USER_A) as session:
                session.execute(text("SELECT 1"))
                session.commit()

            with Session(pinned) as session:
                context = session.execute(
                    text("SELECT current_setting('app.current_user_id', true)")
                ).scalar()
                owners = set(session.execute(text("SELECT cl_1b FROM tb_1")).scalars().all())
        finally:
            pinned.dispose()

        assert context == ""
        assert {USER_A, USER_B} <= owners
