import enum

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUIDBase, enum_column


class UserStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class UserPlan(enum.StrEnum):
    FREE = "free"
    VIP = "vip"
    SVIP = "svip"


class User(UUIDBase):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[UserStatus] = mapped_column(
        enum_column(UserStatus),
        default=UserStatus.PENDING,
        server_default=UserStatus.PENDING.value,
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    plan: Mapped[UserPlan] = mapped_column(
        enum_column(UserPlan),
        default=UserPlan.FREE,
        server_default=UserPlan.FREE.value,
    )
    agent_input_limit: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    agent_input_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    agent_output_limit: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    agent_output_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    edit_limit: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    edit_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    @property
    def can_use_workspace(self) -> bool:
        return self.is_admin or self.status is UserStatus.APPROVED
