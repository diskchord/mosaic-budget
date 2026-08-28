"""Initial durable budgeting ledger.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-27
"""
from __future__ import annotations

from alembic import op

from app.db import Base
from app import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    Base.metadata.create_all(bind=bind)

    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX uq_sections_single_income "
            "ON sections (workspace_id) WHERE is_income IS TRUE"
        )
        op.execute(
            "CREATE UNIQUE INDEX uq_users_single_admin "
            "ON users (workspace_id) WHERE is_admin IS TRUE"
        )
        op.execute(
            "CREATE UNIQUE INDEX uq_incidents_open_key "
            "ON notification_incidents (workspace_id, incident_key) WHERE status = 'open'"
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION mosaic_check_allocation_sum(p_transaction_id uuid)
            RETURNS void AS $$
            DECLARE
                parent_amount numeric(20,4);
                allocation_total numeric(20,4);
                allocation_count integer;
            BEGIN
                SELECT amount INTO parent_amount
                FROM budget_transactions
                WHERE id = p_transaction_id;

                IF parent_amount IS NULL THEN
                    RETURN;
                END IF;

                SELECT count(*), COALESCE(sum(amount), 0)
                INTO allocation_count, allocation_total
                FROM allocations
                WHERE transaction_id = p_transaction_id;

                IF allocation_count > 0 AND allocation_total <> parent_amount THEN
                    RAISE EXCEPTION 'Allocations for transaction % total %, expected %',
                        p_transaction_id, allocation_total, parent_amount
                        USING ERRCODE = '23514';
                END IF;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION mosaic_allocation_trigger()
            RETURNS trigger AS $$
            BEGIN
                PERFORM mosaic_check_allocation_sum(COALESCE(NEW.transaction_id, OLD.transaction_id));
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE CONSTRAINT TRIGGER allocations_sum_to_parent
            AFTER INSERT OR UPDATE OR DELETE ON allocations
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION mosaic_allocation_trigger();
            """
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION mosaic_transaction_amount_trigger()
            RETURNS trigger AS $$
            BEGIN
                IF NEW.amount IS DISTINCT FROM OLD.amount THEN
                    PERFORM mosaic_check_allocation_sum(NEW.id);
                END IF;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE CONSTRAINT TRIGGER transaction_amount_matches_allocations
            AFTER UPDATE OF amount ON budget_transactions
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION mosaic_transaction_amount_trigger();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS mosaic_transaction_amount_trigger() CASCADE")
        op.execute("DROP FUNCTION IF EXISTS mosaic_allocation_trigger() CASCADE")
        op.execute("DROP FUNCTION IF EXISTS mosaic_check_allocation_sum(uuid) CASCADE")
    Base.metadata.drop_all(bind=bind)
