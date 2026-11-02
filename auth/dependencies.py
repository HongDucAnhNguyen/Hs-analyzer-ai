"""FastAPI dependencies for authentication

Simple Bearer Token authentication.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import bcrypt

from auth.security import decode_token, get_user
from auth.models import User

# =============================================================================
# HTTP Bearer Scheme (simple token input)
# =============================================================================

security = HTTPBearer(
    scheme_name="Bearer Token",
    description="Enter your JWT access token"
)


# =============================================================================
# Dependency Functions
# =============================================================================

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> User:
    """
    Dependency to get the current authenticated user from Bearer token.
    
    Usage in endpoint:
        @router.get("/protected")
        async def protected_route(current_user: Annotated[User, Depends(get_current_user)]):
            return {"message": f"Hello, {current_user.username}!"}
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    token_data = decode_token(token)
    
    if token_data is None:
        raise credentials_exception
        
    user = get_user(token_data.username)
    if user is None:
        raise credentials_exception
        
    return User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        disabled=user.disabled,
        role=user.role
    )


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Dependency to get the current active (non-disabled) user.
    """
    if current_user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Inactive user"
        )
    return current_user


def _get_engagement_code_hashes() -> list[str]:
    raw = os.getenv("ENGAGEMENT_CODE_HASHES", "").strip()
    if not raw:
        return []
    return [value.strip() for value in raw.split(",") if value.strip()]


async def require_engagement_code(
    engagement_code: Annotated[str | None, Header(alias="X-Engagement-Code")] = None
) -> None:
    hashes = _get_engagement_code_hashes()
    if not hashes:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Engagement code validation is not configured",
        )

    if not engagement_code:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Engagement code is required",
        )

    for hashed in hashes:
        try:
            if bcrypt.checkpw(engagement_code.encode("utf-8"), hashed.encode("utf-8")):
                return
        except ValueError:
            continue

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid engagement code",
    )
