"""row level security policies

Revision ID: 20260831_02
Revises: 20260831_01
Create Date: 2026-08-31

`rlsContext.py` has always set `app.current_user_id`, and `getDbWithRLS` has
always called it, but no migration ever issued `ENABLE ROW LEVEL SECURITY` or
`CREATE POLICY` — so on a real database that `set_config` was a no-op and every
row was reachable by every session. `docs/TODO.md` called RLS complete; the
integration conftest says the test database must have "all Alembic migrations
applied, including the RLS policies". This is the file both were describing.

This is defence in depth, not the access-control layer. The services still do
their own ownership checks and still enforce the rules RLS cannot see (§3.3
blocking, deleted/banned visibility). What this adds is a floor: a repository
that forgets its `WHERE owner_id = :me`, or a service that trusts a user-supplied
id, returns nothing instead of someone else's recovery data.

## The two things that shape every policy below

**1. No context means no restriction.** Policies read
`app_current_user_id()`, which is NULL when nothing set the session variable.
When it is NULL every policy passes. That is not an oversight — several paths
legitimately touch rows that belong to no single user, and all of them run
without a context:

  - `/auth/*` (register, login, refresh) uses `getDb`, deliberately without a
    user: at that point there is no authenticated user to scope to.
  - `fcmService.sendPushToUser` opens its own session to read *another* user's
    device tokens — that is the whole point of a server-side push fan-out.
  - `userBadgesRepository` takes a session in its constructor rather than the
    request's, so its queries never carry the request's context.

  Fail-closed would break all three, silently, as empty results. So the escape
  is explicit and documented rather than discovered later.

**2. Users stay readable across accounts.** `tb_0` is the one table whose
SELECT is unrestricted. Friend search matches an exact username or email
(§5), public profiles are a feature, and friendship and chat responses are
enriched with the other participant's name. Restricting SELECT here would break
all of it. What the policies do restrict is UPDATE and DELETE: a session may
read any user row and modify only its own.

## Ownership is the Firebase UID

`tb_0.cl_0a` is a VARCHAR holding the Firebase UID, and every FK to it is a
VARCHAR too, so the comparisons below are text = text with no cast.

## This is inert for a role with BYPASSRLS

FORCE ROW LEVEL SECURITY makes the policies apply to the table owner, which is
what the application connects as. It does *not* override the BYPASSRLS role
attribute or a real superuser. The end of `upgrade()` checks the current role
and prints a warning rather than failing, because on a managed instance the
migration role is not always the application role.
"""

from alembic import op
import sqlalchemy as sa

from core.config import config as appConfig


revision = "20260831_02"
down_revision = "20260831_01"
branch_labels = None
depends_on = None


# Every policy is written against this rather than repeating the
# current_setting call. `nullif` collapses the two shapes of "no context" —
# never set (NULL) and cleared to the empty string — into one, so a policy only
# has to test IS NULL. STABLE and language sql so the planner inlines it.
CREATE_HELPER = """
CREATE OR REPLACE FUNCTION app_current_user_id() RETURNS text
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$ SELECT nullif(current_setting('app.current_user_id', true), '') $$;

COMMENT ON FUNCTION app_current_user_id() IS
  'The authenticated user for the current session, or NULL when no context was set. See migration 20260831_02.';
"""

# (table, [(policy name, FOR clause, USING or None, WITH CHECK or None)])
#
# `ctx` below is app_current_user_id(). Read every expression as: no context, or
# the row belongs to the session's user.
POLICIES: list[tuple[str, list[tuple[str, str, str | None, str | None]]]] = [
    # ── tb_0 users ──────────────────────────────────────────────────────────
    # Readable by everyone (search, public profiles, enriched responses),
    # writable only by its owner.
    ("tb_0", [
        ("tb_0_select_any", "SELECT", "true", None),
        ("tb_0_insert_any", "INSERT", None, "true"),
        ("tb_0_update_own", "UPDATE",
         "app_current_user_id() IS NULL OR cl_0a = app_current_user_id()",
         "app_current_user_id() IS NULL OR cl_0a = app_current_user_id()"),
        ("tb_0_delete_own", "DELETE",
         "app_current_user_id() IS NULL OR cl_0a = app_current_user_id()", None),
    ]),

    # ── tb_1 streaks ────────────────────────────────────────────────────────
    # The most private table in the schema: a streak is a record of someone's
    # relapses. Nothing in the app reads another user's streak — the public
    # profile renders a placeholder — so this is closed in every direction.
    ("tb_1", [
        ("tb_1_owner", "ALL",
         "app_current_user_id() IS NULL OR cl_1b = app_current_user_id()",
         "app_current_user_id() IS NULL OR cl_1b = app_current_user_id()"),
    ]),

    # ── tb_2 friendships ────────────────────────────────────────────────────
    # Either side of the pair. Both directions are needed: the receiver accepts,
    # rejects and blocks, so restricting to the sender would break every reply
    # to a request.
    ("tb_2", [
        ("tb_2_participant", "ALL",
         "app_current_user_id() IS NULL OR cl_2b = app_current_user_id() OR cl_2c = app_current_user_id()",
         "app_current_user_id() IS NULL OR cl_2b = app_current_user_id() OR cl_2c = app_current_user_id()"),
    ]),

    # ── tb_3 chats ──────────────────────────────────────────────────────────
    ("tb_3", [
        ("tb_3_participant", "ALL",
         "app_current_user_id() IS NULL OR cl_3b = app_current_user_id() OR cl_3c = app_current_user_id()",
         "app_current_user_id() IS NULL OR cl_3b = app_current_user_id() OR cl_3c = app_current_user_id()"),
    ]),

    # ── tb_4 messages ───────────────────────────────────────────────────────
    # Scoped through the chat, not through the sender: marking a message read is
    # an UPDATE the *recipient* performs on the *sender's* row, so a
    # sender-based rule would break read receipts. INSERT is the one command
    # that also pins the sender — you may write into your own chats, as
    # yourself.
    ("tb_4", [
        ("tb_4_select_participant", "SELECT",
         "app_current_user_id() IS NULL OR EXISTS ("
         "  SELECT 1 FROM tb_3 WHERE tb_3.cl_3a = tb_4.cl_4b"
         "     AND (tb_3.cl_3b = app_current_user_id() OR tb_3.cl_3c = app_current_user_id()))",
         None),
        ("tb_4_insert_own", "INSERT", None,
         "app_current_user_id() IS NULL OR (cl_4c = app_current_user_id() AND EXISTS ("
         "  SELECT 1 FROM tb_3 WHERE tb_3.cl_3a = tb_4.cl_4b"
         "     AND (tb_3.cl_3b = app_current_user_id() OR tb_3.cl_3c = app_current_user_id())))"),
        ("tb_4_update_participant", "UPDATE",
         "app_current_user_id() IS NULL OR EXISTS ("
         "  SELECT 1 FROM tb_3 WHERE tb_3.cl_3a = tb_4.cl_4b"
         "     AND (tb_3.cl_3b = app_current_user_id() OR tb_3.cl_3c = app_current_user_id()))",
         "app_current_user_id() IS NULL OR EXISTS ("
         "  SELECT 1 FROM tb_3 WHERE tb_3.cl_3a = tb_4.cl_4b"
         "     AND (tb_3.cl_3b = app_current_user_id() OR tb_3.cl_3c = app_current_user_id()))"),
        ("tb_4_delete_own", "DELETE",
         "app_current_user_id() IS NULL OR cl_4c = app_current_user_id()", None),
    ]),

    # ── tb_6 user badges ────────────────────────────────────────────────────
    # tb_5, the badge catalogue itself, gets no RLS at all: it is the same ten
    # rows for everybody and every session has to read it.
    ("tb_6", [
        ("tb_6_owner", "ALL",
         "app_current_user_id() IS NULL OR cl_6b = app_current_user_id()",
         "app_current_user_id() IS NULL OR cl_6b = app_current_user_id()"),
    ]),

    # ── tb_7 audit logs ─────────────────────────────────────────────────────
    # Append-only, and readable only about yourself. There are no UPDATE or
    # DELETE policies, which is what makes the table append-only: a command with
    # no policy is denied outright once RLS is on. `GET /logs` is authenticated
    # but not privileged, so before this every user could read the whole audit
    # trail — including entries about other people.
    #
    # INSERT stays open because a log entry is not always about the session's
    # own user (a friendship event names the other party) and the column is
    # nullable for events that name nobody.
    ("tb_7", [
        ("tb_7_select_own", "SELECT",
         "app_current_user_id() IS NULL OR cl_7c = app_current_user_id()", None),
        ("tb_7_insert_any", "INSERT", None, "true"),
    ]),

    # ── tb_8 refresh tokens ─────────────────────────────────────────────────
    # No repository reads this table yet — the model exists and nothing queries
    # it. The policy is here so that whoever wires it up inherits the rule
    # instead of having to remember it. /auth/refresh runs without a context and
    # is unaffected either way.
    ("tb_8", [
        ("tb_8_owner", "ALL",
         "app_current_user_id() IS NULL OR cl_8b = app_current_user_id()",
         "app_current_user_id() IS NULL OR cl_8b = app_current_user_id()"),
    ]),

    # ── tb_9 device tokens ──────────────────────────────────────────────────
    # An FCM token is a handle for delivering to someone's phone. Registration
    # goes through an authenticated request and is scoped; the push fan-out
    # reads other users' tokens from a session with no context and passes on
    # the escape above.
    ("tb_9", [
        ("tb_9_owner", "ALL",
         "app_current_user_id() IS NULL OR cl_9b = app_current_user_id()",
         "app_current_user_id() IS NULL OR cl_9b = app_current_user_id()"),
    ]),
]


# Every policy above adds a predicate on one of these columns to *every* query
# against its table, including the ones the services already filter themselves.
# None of them was indexed — the baseline schema indexes primary keys and the
# two lookup hashes on tb_0 and nothing else — so without this the policies turn
# each read into a sequential scan. Named after the column so a future
# autogenerate does not propose them again under a different name.
#
# tb_4 is indexed on the chat rather than the sender: the policy resolves a
# message through tb_3, so the chat is the column it filters on.
POLICY_INDEXES = [
    ("tb_1", "cl_1b"),  # streak owner
    ("tb_2", "cl_2b"),  # friendship sender
    ("tb_2", "cl_2c"),  # friendship receiver
    ("tb_3", "cl_3b"),  # chat sender
    ("tb_3", "cl_3c"),  # chat receiver
    ("tb_4", "cl_4b"),  # message chat
    ("tb_6", "cl_6b"),  # user badge owner
    ("tb_7", "cl_7c"),  # audit log catalyst
    ("tb_9", "cl_9b"),  # device token owner
]


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(CREATE_HELPER))

    for table, column in POLICY_INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table} ({column})")

    for table, policies in POLICIES:
        # ENABLE turns policies on for everyone except the table's owner; FORCE
        # is what extends them to the owner as well. The application connects as
        # the owner, so without FORCE this whole file would be decoration.
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        for name, command, using, check in policies:
            sql = f"CREATE POLICY {name} ON {table} FOR {command} TO PUBLIC"
            if using is not None:
                sql += f" USING ({using})"
            if check is not None:
                sql += f" WITH CHECK ({check})"
            op.execute(sql)

    _warnIfPoliciesAreInert(connection)


def downgrade() -> None:
    for table, column in POLICY_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_{column}")

    for table, policies in POLICIES:
        for name, _, _, _ in policies:
            op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP FUNCTION IF EXISTS app_current_user_id()")


def _warnIfPoliciesAreInert(connection) -> None:
    """A superuser or a BYPASSRLS role ignores every policy created above.

    Checks the role the *application* connects as, not only the one running the
    migration — they are frequently different, and only the first one decides
    whether any of this has an effect at runtime. Printed rather than raised: a
    migration that refuses to apply because of how some other role is
    configured blocks a deploy over something it cannot fix.
    """
    appRole = getattr(appConfig, "DATABASE_USER", None)

    rows = connection.execute(
        sa.text(
            """
            SELECT rolname, rolsuper, rolbypassrls
              FROM pg_roles
             WHERE rolname = current_user OR rolname = :appRole
            """
        ),
        {"appRole": appRole},
    ).fetchall()

    for name, isSuper, bypasses in rows:
        if not (isSuper or bypasses):
            continue

        attribute = "SUPERUSER" if isSuper else "BYPASSRLS"
        isAppRole = name == appRole
        role = "the application role" if isAppRole else "the migration role"
        consequence = (
            "RLS is off for the running application, whatever this file says"
            if isAppRole
            else "harmless on its own — a migration is supposed to see everything"
        )

        print(
            "\n  WARNING: {} ({}) has {}, which ignores every policy\n"
            "  this migration created. {}.\n"
            "  Give the application a role with NOBYPASSRLS and no superuser bit,\n"
            "  granted SELECT/INSERT/UPDATE/DELETE on the tables it uses.\n".format(
                role, name, attribute, consequence
            )
        )
