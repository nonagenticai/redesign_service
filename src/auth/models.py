"""User model for authentication."""

from __future__ import annotations

from pydantic import BaseModel, Field


class User(BaseModel):
    """User model extracted from license token introspection."""

    sub: str = Field(..., description="User/Tenant ID")
    preferred_username: str = Field(default="anonymous", description="Username")
    tenant_id: str | None = None

    @property
    def effective_tenant_id(self) -> str:
        return self.tenant_id or self.sub
