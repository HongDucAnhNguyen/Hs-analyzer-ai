"""Authentication router - Login, Refresh, and Logout endpoints

Endpoints:
- POST /auth/login - Login with username/password (JSON), get access & refresh tokens
- POST /auth/refresh - Refresh access token using refresh token
- POST /auth/logout - Logout and invalidate current token
"""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth.config import ACCESS_TOKEN_EXPIRE_MINUTES, get_auth_token_version
from auth.models import Token, LoginRequest, RefreshTokenRequest
from auth.security import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_user,
    add_token_to_blacklist,
)

security = HTTPBearer()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# =============================================================================
# Login Endpoint
# =============================================================================

@router.post("/login", response_model=Token)
async def login(request: LoginRequest):
    """
    Login with username and password.
    
    Returns JWT access token and refresh token.
    """
    user = authenticate_user(request.username, request.password)

    if not user:
        logger.warning(f"Failed login attempt for user: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create tokens with user info
    token_data = {
        "sub": user.username,
        "role": user.role,
        "email": user.email,
        "ver": get_auth_token_version(),
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    logger.info(f"User logged in successfully: {user.username}")
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


# =============================================================================
# Refresh Token Endpoint
# =============================================================================

@router.post("/refresh", response_model=Token)
async def refresh(request: RefreshTokenRequest):
    """
    Get a new access token using a refresh token.
    
    **Example:**
    ```json
    {
        "refresh_token": "<your_refresh_token>"
    }
    ```
    """
    token_data = decode_refresh_token(request.refresh_token)
    
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify user still exists and is active
    user = get_user(token_data.username)
    if user is None or user.disabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create new tokens
    new_token_data = {
        "sub": user.username,
        "role": user.role,
        "email": user.email,
        "ver": get_auth_token_version(),
    }
    
    access_token = create_access_token(new_token_data)
    refresh_token = create_refresh_token(new_token_data)
    
    logger.info(f"Tokens refreshed for user: {user.username}")
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


# =============================================================================
# Logout Endpoint
# =============================================================================

@router.post("/logout")
async def logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
):
    """
    Logout and invalidate the current access token.
    
    Requires Bearer token in Authorization header.
    
    After logout, the token will no longer be valid for any API calls.
    """
    token = credentials.credentials
    
    # Add token to blacklist
    add_token_to_blacklist(token)
    
    logger.info("User logged out, token invalidated")
    
    return {
        "message": "Successfully logged out",
        "detail": "Token has been invalidated"
    }
