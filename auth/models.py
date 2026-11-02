"""Authentication models for Pydantic validation"""

from typing import Optional
from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    """JWT Token response model"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class TokenData(BaseModel):
    """Data extracted from JWT token"""
    username: Optional[str] = None
    role: Optional[str] = None
    token_version: Optional[str] = None


class User(BaseModel):
    """User model for API responses (without password)"""
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    role: str = "user"


class UserInDB(User):
    """User model with hashed password (internal use only)"""
    hashed_password: str


class LoginRequest(BaseModel):
    """Login request body"""
    username: str
    password: str
    
    # model_config = {
    #     "json_schema_extra": {
    #         "examples": [
    #             {
    #                 "username": "admin",
    #                 "password": "admin123"
    #             }
    #         ]
    #     }
    # }


class RefreshTokenRequest(BaseModel):
    """Refresh token request body"""
    refresh_token: str

