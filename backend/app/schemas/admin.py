from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserPlan, UserStatus
from app.schemas.auth import UserOut


class UserAdminPatch(BaseModel):
    status: UserStatus | None = None
    plan: UserPlan | None = None
    agent_input_limit: int | None = Field(default=None, ge=0, le=1_000_000)
    agent_output_limit: int | None = Field(default=None, ge=0, le=1_000_000)
    edit_limit: int | None = Field(default=None, ge=0, le=1_000_000)


class AdminUserOut(UserOut):
    model_config = ConfigDict(from_attributes=True)
