import uuid

from pydantic import BaseModel, Field, field_validator

from app.models.user import UserPlan, UserStatus


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=64)

    @field_validator("username")
    @classmethod
    def _normalize(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.replace("_", "").isalnum():
            raise ValueError("用户名只能包含字母、数字和下划线")
        return normalized


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    status: UserStatus
    is_admin: bool
    plan: UserPlan
    agent_input_limit: int
    agent_input_used: int
    agent_output_limit: int
    agent_output_used: int
    edit_limit: int
    edit_used: int

    model_config = {"from_attributes": True}
