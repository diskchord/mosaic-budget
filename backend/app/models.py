from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

JSONType = JSON().with_variant(JSONB, "postgresql")
MONEY = Numeric(20, 4)
STRUCTURE_EPOCH = date(1900, 1, 1)


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class VersionMixin:
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)


class Workspace(Base, UUIDMixin, TimestampMixin, VersionMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(160), nullable=False, default="Household Budget")
    currency: Mapped[str] = mapped_column(String(255), nullable=False, default="USD")

    users: Mapped[list[User]] = relationship(back_populates="workspace")
    sections: Mapped[list[Section]] = relationship(back_populates="workspace")


class User(Base, UUIDMixin, TimestampMixin, VersionMixin):
    __tablename__ = "users"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    theme: Mapped[str] = mapped_column(String(40), nullable=False, default="citrus", server_default="citrus")
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict, server_default="{}")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workspace: Mapped[Workspace] = relationship(back_populates="users")
    sessions: Mapped[list[SessionRecord]] = relationship(back_populates="user", cascade="all, delete-orphan")


class SessionRecord(Base, UUIDMixin):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    ip_address: Mapped[str] = mapped_column(String(80), nullable=False, default="")

    user: Mapped[User] = relationship(back_populates="sessions")


class LoginThrottle(Base):
    __tablename__ = "login_throttles"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Section(Base, UUIDMixin, TimestampMixin, VersionMixin):
    __tablename__ = "sections"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="section_sort_nonnegative"),
        CheckConstraint("date_part('day', starts_month) = 1", name="section_starts_month_first_day"),
        CheckConstraint(
            "ends_before_month IS NULL OR date_part('day', ends_before_month) = 1",
            name="section_ends_month_first_day",
        ),
        CheckConstraint(
            "ends_before_month IS NULL OR ends_before_month >= starts_month",
            name="section_month_range_valid",
        ),
        Index("ix_sections_workspace_sort", "workspace_id", "is_income", "sort_order"),
        Index("ix_sections_workspace_lifetime", "workspace_id", "starts_month", "ends_before_month"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str] = mapped_column(String(40), nullable=False, default="wallet", server_default="wallet")
    accent: Mapped[str] = mapped_column(String(40), nullable=False, default="accent", server_default="accent")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_income: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    starts_month: Mapped[date] = mapped_column(
        Date, nullable=False, default=STRUCTURE_EPOCH, server_default="1900-01-01"
    )
    ends_before_month: Mapped[date | None] = mapped_column(Date)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workspace: Mapped[Workspace] = relationship(back_populates="sections")
    categories: Mapped[list[Category]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="Category.sort_order"
    )
    month_exclusions: Mapped[list[SectionMonthExclusion]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )


class Category(Base, UUIDMixin, TimestampMixin, VersionMixin):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="category_sort_nonnegative"),
        CheckConstraint("date_part('day', starts_month) = 1", name="category_starts_month_first_day"),
        CheckConstraint(
            "ends_before_month IS NULL OR date_part('day', ends_before_month) = 1",
            name="category_ends_month_first_day",
        ),
        CheckConstraint(
            "ends_before_month IS NULL OR ends_before_month >= starts_month",
            name="category_month_range_valid",
        ),
        Index("ix_categories_section_sort", "section_id", "sort_order"),
        Index("ix_categories_section_lifetime", "section_id", "starts_month", "ends_before_month"),
    )

    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rollover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    default_planned: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"), server_default="0")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    starts_month: Mapped[date] = mapped_column(
        Date, nullable=False, default=STRUCTURE_EPOCH, server_default="1900-01-01"
    )
    ends_before_month: Mapped[date | None] = mapped_column(Date)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    section: Mapped[Section] = relationship(back_populates="categories")
    budgets: Mapped[list[CategoryBudget]] = relationship(back_populates="category", cascade="all, delete-orphan")
    month_exclusions: Mapped[list[CategoryMonthExclusion]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class SectionMonthExclusion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "section_month_exclusions"
    __table_args__ = (
        UniqueConstraint("section_id", "month", name="uq_section_month_exclusion"),
        CheckConstraint("date_part('day', month) = 1", name="section_exclusion_month_first_day"),
        Index("ix_section_month_exclusions_month", "month", "section_id"),
    )

    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)

    section: Mapped[Section] = relationship(back_populates="month_exclusions")


class CategoryMonthExclusion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "category_month_exclusions"
    __table_args__ = (
        UniqueConstraint("category_id", "month", name="uq_category_month_exclusion"),
        CheckConstraint("date_part('day', month) = 1", name="category_exclusion_month_first_day"),
        Index("ix_category_month_exclusions_month", "month", "category_id"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)

    category: Mapped[Category] = relationship(back_populates="month_exclusions")


class CategoryBudget(Base, UUIDMixin, TimestampMixin, VersionMixin):
    __tablename__ = "category_budgets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "month", "category_id", name="uq_category_budget_month_category"),
        CheckConstraint("date_part('day', month) = 1", name="budget_month_first_day"),
        Index("ix_category_budgets_workspace_month", "workspace_id", "month"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    planned: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"), server_default="0")

    category: Mapped[Category] = relationship(back_populates="budgets")


class SimpleFinConnection(Base, UUIDMixin, TimestampMixin, VersionMixin):
    __tablename__ = "simplefin_connections"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False, default="SimpleFIN")
    encrypted_access_url: Mapped[str | None] = mapped_column(Text)
    access_url_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    schedule_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=17)
    next_sync_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_deep_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error_code: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    last_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    accounts: Mapped[list[Account]] = relationship(back_populates="simplefin_connection")
    provider_connections: Mapped[list[InstitutionConnection]] = relationship(
        back_populates="simplefin_connection", cascade="all, delete-orphan"
    )


class InstitutionConnection(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "institution_connections"
    __table_args__ = (
        UniqueConstraint("simplefin_connection_id", "source_conn_id", name="uq_provider_connection_source"),
    )

    simplefin_connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simplefin_connections.id", ondelete="CASCADE"), nullable=False
    )
    source_conn_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    org_id: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    org_url: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    sfin_url: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    simplefin_connection: Mapped[SimpleFinConnection] = relationship(back_populates="provider_connections")


class Account(Base, UUIDMixin, TimestampMixin, VersionMixin):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint(
            "simplefin_connection_id", "source_conn_id", "source_account_id", name="uq_account_source_identity"
        ),
        Index("ix_accounts_workspace_active", "workspace_id", "is_active"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    simplefin_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("simplefin_connections.id", ondelete="CASCADE")
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="simplefin", server_default="simplefin")
    source_conn_id: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    source_account_id: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(255), nullable=False, default="USD", server_default="USD")
    balance: Mapped[Decimal | None] = mapped_column(MONEY)
    available_balance: Mapped[Decimal | None] = mapped_column(MONEY)
    balance_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_budget: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    extra: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict, server_default="{}")

    simplefin_connection: Mapped[SimpleFinConnection | None] = relationship(back_populates="accounts")
    transactions: Mapped[list[BudgetTransaction]] = relationship(back_populates="account")


class SyncRun(Base, UUIDMixin):
    __tablename__ = "sync_runs"
    __table_args__ = (Index("ix_sync_runs_connection_started", "simplefin_connection_id", "started_at"),)

    simplefin_connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simplefin_connections.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="routine")
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accounts_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    transactions_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    transactions_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    transactions_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    errors_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_code: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")


class ImportBatch(Base, UUIDMixin):
    __tablename__ = "import_batches"
    __table_args__ = (Index("ix_import_batches_connection_received", "simplefin_connection_id", "received_at"),)

    simplefin_connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simplefin_connections.id", ondelete="CASCADE"), nullable=False
    )
    sync_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)


class BudgetTransaction(Base, UUIDMixin, TimestampMixin, VersionMixin):
    __tablename__ = "budget_transactions"
    __table_args__ = (
        Index("ix_budget_transactions_workspace_date", "workspace_id", "effective_date"),
        Index("ix_budget_transactions_unassigned", "workspace_id", "deleted_at", "excluded", "effective_date"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="simplefin")
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payee: Mapped[str] = mapped_column(String(500), nullable=False)
    imported_description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    imported_extra: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict, server_default="{}")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    tags: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list, server_default="[]")
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    cleared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    suppressed_by_duplicate_account: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    manual_payee_lock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    manual_date_lock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    manual_allocation_lock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    transfer_group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    account: Mapped[Account] = relationship(back_populates="transactions")
    allocations: Mapped[list[Allocation]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", order_by="Allocation.sort_order"
    )
    source_records: Mapped[list[SourceTransaction]] = relationship(back_populates="budget_transaction")


class SourceTransaction(Base, UUIDMixin):
    __tablename__ = "source_transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "source_transaction_id", name="uq_source_transaction_account_id"),
        Index("ix_source_transactions_budget_transaction", "budget_transaction_id"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    source_transaction_id: Mapped[str] = mapped_column(String(500), nullable=False)
    budget_transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("budget_transactions.id", ondelete="CASCADE"), nullable=False
    )
    first_seen_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False)
    last_seen_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_transactions.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    budget_transaction: Mapped[BudgetTransaction] = relationship(back_populates="source_records")
    versions: Mapped[list[SourceTransactionVersion]] = relationship(
        back_populates="source_transaction", cascade="all, delete-orphan"
    )


class SourceTransactionVersion(Base, UUIDMixin):
    __tablename__ = "source_transaction_versions"
    __table_args__ = (
        UniqueConstraint("source_transaction_id", "content_hash", name="uq_source_version_content"),
        Index("ix_source_versions_source_observed", "source_transaction_id", "observed_at"),
    )

    source_transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_transactions.id", ondelete="CASCADE"), nullable=False
    )
    import_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict, server_default="{}")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    source_transaction: Mapped[SourceTransaction] = relationship(back_populates="versions")


class Allocation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "allocations"
    __table_args__ = (
        UniqueConstraint("transaction_id", "sort_order", name="uq_allocation_transaction_sort"),
        Index("ix_allocations_category", "category_id"),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("budget_transactions.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    memo: Mapped[str] = mapped_column(String(300), nullable=False, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applied_by_rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rules.id", ondelete="SET NULL"))

    transaction: Mapped[BudgetTransaction] = relationship(back_populates="allocations")
    category: Mapped[Category] = relationship()


class Rule(Base, UUIDMixin, TimestampMixin, VersionMixin):
    __tablename__ = "rules"
    __table_args__ = (
        Index("ix_rules_workspace_enabled", "workspace_id", "enabled", "phase", "priority"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    phase: Mapped[str] = mapped_column(String(20), nullable=False, default="categorize")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict, server_default="{}")
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list, server_default="[]")
    apply_to_manual_overrides: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    stop_processing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class RuleRevision(Base, UUIDMixin):
    __tablename__ = "rule_revisions"
    __table_args__ = (UniqueConstraint("rule_id", "version", name="uq_rule_revision_version"),)

    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditEvent(Base, UUIDMixin):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_workspace_created", "workspace_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NotificationIncident(Base, UUIDMixin):
    __tablename__ = "notification_incidents"
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    incident_key: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default="open")
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        Index("ix_incidents_workspace_status", "workspace_id", "status", "last_seen_at"),
    )


class NotificationOutbox(Base, UUIDMixin):
    __tablename__ = "notification_outbox"
    __table_args__ = (Index("ix_outbox_due", "status", "next_attempt_at"),)

    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("notification_incidents.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BalanceAlert(Base, UUIDMixin, TimestampMixin, VersionMixin):
    __tablename__ = "balance_alerts"
    __table_args__ = (
        CheckConstraint("comparison IN ('below', 'above')", name="balance_alert_comparison_valid"),
        Index("ix_balance_alerts_workspace_enabled", "workspace_id", "enabled"),
        Index(
            "ix_balance_alerts_workspace_account_enabled",
            "workspace_id",
            "account_id",
            "enabled",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    comparison: Mapped[str] = mapped_column(String(12), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    channels: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list, server_default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    account: Mapped[Account] = relationship()


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(80), primary_key=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict, server_default="{}")


class SimpleFinRequestLog(Base, UUIDMixin):
    __tablename__ = "simplefin_request_log"
    __table_args__ = (Index("ix_simplefin_request_connection_time", "simplefin_connection_id", "requested_at"),)

    simplefin_connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simplefin_connections.id", ondelete="CASCADE"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(30), nullable=False, default="accounts")
    status_code: Mapped[int | None] = mapped_column(Integer)


class BackupRecord(Base, UUIDMixin):
    __tablename__ = "backup_records"

    path: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
