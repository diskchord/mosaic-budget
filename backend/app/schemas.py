from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserCreateRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=14, max_length=500)
    is_admin: bool = False


class UserUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=14, max_length=500)


class PreferenceRequest(BaseModel):
    version: int = Field(ge=1)
    theme: str | None = Field(default=None, max_length=40)
    preferences: dict[str, Any] | None = None


class SectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    icon: str = Field(default="wallet", max_length=40)
    accent: str = Field(default="accent", max_length=40)
    sort_order: int | None = Field(default=None, ge=0)
    starts_month: date | None = None


class SectionUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = Field(default=None, max_length=40)
    accent: str | None = Field(default=None, max_length=40)
    sort_order: int | None = Field(default=None, ge=0)


class CategoryCreateRequest(BaseModel):
    section_id: UUID
    name: str = Field(min_length=1, max_length=120)
    sort_order: int | None = Field(default=None, ge=0)
    rollover: bool = False
    default_planned: str = "0"
    note: str = Field(default="", max_length=4000)
    starts_month: date | None = None


class CategoryUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    section_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = Field(default=None, ge=0)
    rollover: bool | None = None
    default_planned: str | None = None
    note: str | None = Field(default=None, max_length=4000)


class StructureVisibilityRequest(BaseModel):
    version: int = Field(ge=1)
    month: date
    visible: bool
    scope: Literal["month", "forward", "all"]


class BudgetAmountRequest(BaseModel):
    version: int = Field(ge=0)
    planned: str


class AllocationInput(BaseModel):
    category_id: UUID
    amount: str
    memo: str = Field(default="", max_length=300)


class AllocationRequest(BaseModel):
    version: int = Field(ge=1)
    allocations: list[AllocationInput] = Field(default_factory=list, max_length=100)


class TransactionUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    payee: str | None = Field(default=None, min_length=1, max_length=500)
    effective_date: date | None = None
    allocations: list[AllocationInput] | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=10000)
    tags: list[str] | None = Field(default=None, max_length=50)
    cleared: bool | None = None
    excluded: bool | None = None
    needs_review: bool | None = None


class ManualTransactionRequest(BaseModel):
    account_id: UUID
    effective_date: date
    amount: str
    payee: str = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=10000)
    allocations: list[AllocationInput] = Field(default_factory=list, max_length=100)


class DeleteTransactionRequest(BaseModel):
    version: int = Field(ge=1)
    confirm: Literal[True]
    confirm_amount: str


class RuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    enabled: bool = True
    phase: Literal["cleanup", "categorize", "finish"] = "categorize"
    priority: int = Field(default=100, ge=0, le=100000)
    conditions: dict[str, Any]
    actions: list[dict[str, Any]] = Field(min_length=1, max_length=50)
    apply_to_manual_overrides: bool = False
    stop_processing: bool = True
    apply_now: Literal["none", "unassigned", "eligible"] = "none"


class RuleUpdateRequest(RuleRequest):
    version: int = Field(ge=1)


class RuleRunRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")


class SimpleFinClaimRequest(BaseModel):
    setup_token: str = Field(min_length=20, max_length=10000)
    name: str = Field(default="SimpleFIN", min_length=1, max_length=160)


class IncidentAcknowledgeRequest(BaseModel):
    acknowledged: bool = True
