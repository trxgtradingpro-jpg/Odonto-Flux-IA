from pydantic import BaseModel, EmailStr, Field


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TokenOutput(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'
    expires_in: int


class RefreshInput(BaseModel):
    refresh_token: str


class PasswordResetRequestInput(BaseModel):
    email: EmailStr


class PasswordResetConfirmInput(BaseModel):
    token: str
    new_password: str = Field(min_length=10)
