from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserOut


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(json_schema_extra={"example": {"login": "clerk", "password": "clerk123"}})


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Время жизни токена, секунды")
    user: UserOut


class MeResponse(UserOut):
    permissions: list[str] = Field(default_factory=list, description="Разрешения роли (матрица RBAC)")
