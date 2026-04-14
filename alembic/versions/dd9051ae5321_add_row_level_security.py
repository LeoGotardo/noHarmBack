"""add row level security

Revision ID: dd9051ae5321
Revises:
Create Date: 2025-04-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd9051ae5321'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable Row Level Security on all user-data tables."""

    # Create a function to set the current user ID in the session
    op.execute("""
        CREATE OR REPLACE FUNCTION set_current_user_id(user_id UUID)
        RETURNS VOID AS $$
        BEGIN
            PERFORM set_config('app.current_user_id', user_id::text, false);
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)

    # Create a function to get the current user ID from the session
    op.execute("""
        CREATE OR REPLACE FUNCTION get_current_user_id()
        RETURNS UUID AS $$
        BEGIN
            RETURN NULLIF(current_setting('app.current_user_id', true), '')::UUID;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)

    # ============================================
    # Table: tb_0 (users) - Users can only see their own data
    # ============================================
    op.execute("ALTER TABLE tb_0 ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY users_own_data ON tb_0
            FOR ALL
            USING (cl_0a = get_current_user_id())
            WITH CHECK (cl_0a = get_current_user_id());
    """)

    # ============================================
    # Table: tb_1 (streaks) - Users can only see their own streaks
    # ============================================
    op.execute("ALTER TABLE tb_1 ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY streaks_own_data ON tb_1
            FOR ALL
            USING (cl_1b = get_current_user_id())
            WITH CHECK (cl_1b = get_current_user_id());
    """)

    # ============================================
    # Table: tb_2 (friendships) - Users can see friendships they sent or received
    # ============================================
    op.execute("ALTER TABLE tb_2 ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY friendships_participant_data ON tb_2
            FOR ALL
            USING (cl_2b = get_current_user_id() OR cl_2c = get_current_user_id())
            WITH CHECK (cl_2b = get_current_user_id() OR cl_2c = get_current_user_id());
    """)

    # ============================================
    # Table: tb_3 (chats) - Users can see chats they participate in
    # ============================================
    op.execute("ALTER TABLE tb_3 ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY chats_participant_data ON tb_3
            FOR ALL
            USING (cl_3b = get_current_user_id() OR cl_3c = get_current_user_id())
            WITH CHECK (cl_3b = get_current_user_id() OR cl_3c = get_current_user_id());
    """)

    # ============================================
    # Table: tb_4 (messages) - Users can see messages in chats they participate in
    # ============================================
    op.execute("ALTER TABLE tb_4 ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY messages_chat_participant_data ON tb_4
            FOR ALL
            USING (
                cl_4b IN (
                    SELECT cl_3a FROM tb_3
                    WHERE cl_3b = get_current_user_id() OR cl_3c = get_current_user_id()
                )
            )
            WITH CHECK (
                cl_4b IN (
                    SELECT cl_3a FROM tb_3
                    WHERE cl_3b = get_current_user_id() OR cl_3c = get_current_user_id()
                )
            );
    """)

    # Alternative: simpler policy based on sender
    op.execute("""
        CREATE POLICY messages_sender_data ON tb_4
            FOR ALL
            USING (cl_4c = get_current_user_id())
            WITH CHECK (cl_4c = get_current_user_id());
    """)

    # ============================================
    # Table: tb_5 (badges) - Global table, everyone can read
    # ============================================
    op.execute("ALTER TABLE tb_5 ENABLE ROW LEVEL SECURITY;")
    # Badges are global - everyone can read, only system can write
    op.execute("""
        CREATE POLICY badges_read_all ON tb_5
            FOR SELECT
            USING (true);
    """)
    # For INSERT/UPDATE/DELETE, only the application (bypassing RLS or via specific logic)
    # This is typically managed by the application layer

    # ============================================
    # Table: tb_6 (user_badges) - Users can see their own badges
    # ============================================
    op.execute("ALTER TABLE tb_6 ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY user_badges_own_data ON tb_6
            FOR ALL
            USING (cl_6b = get_current_user_id())
            WITH CHECK (cl_6b = get_current_user_id());
    """)

    # ============================================
    # Table: tb_7 (audit_logs) - Users can see their own audit logs
    # ============================================
    op.execute("ALTER TABLE tb_7 ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY audit_logs_own_data ON tb_7
            FOR ALL
            USING (cl_7c = get_current_user_id())
            WITH CHECK (cl_7c = get_current_user_id());
    """)


def downgrade() -> None:
    """Disable Row Level Security."""

    # Drop policies
    op.execute("DROP POLICY IF EXISTS users_own_data ON tb_0;")
    op.execute("DROP POLICY IF EXISTS streaks_own_data ON tb_1;")
    op.execute("DROP POLICY IF EXISTS friendships_participant_data ON tb_2;")
    op.execute("DROP POLICY IF EXISTS chats_participant_data ON tb_3;")
    op.execute("DROP POLICY IF EXISTS messages_chat_participant_data ON tb_4;")
    op.execute("DROP POLICY IF EXISTS messages_sender_data ON tb_4;")
    op.execute("DROP POLICY IF EXISTS badges_read_all ON tb_5;")
    op.execute("DROP POLICY IF EXISTS user_badges_own_data ON tb_6;")
    op.execute("DROP POLICY IF EXISTS audit_logs_own_data ON tb_7;")

    # Disable RLS
    op.execute("ALTER TABLE tb_0 DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tb_1 DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tb_2 DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tb_3 DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tb_4 DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tb_5 DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tb_6 DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tb_7 DISABLE ROW LEVEL SECURITY;")

    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS get_current_user_id();")
    op.execute("DROP FUNCTION IF EXISTS set_current_user_id(UUID);")
