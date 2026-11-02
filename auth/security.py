"""Security utilities for password hashing and JWT token handling"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Set

import bcrypt
from jose import JWTError, jwt

from auth.config import (
    SECRET_KEY,
    ALGORITHM,
    get_users_db,
    get_access_token_expire_delta,
    get_refresh_token_expire_delta,
    get_auth_token_version,
)
from auth.models import TokenData, User, UserInDB


# =============================================================================
# Token Blacklist (in-memory, use Redis in production)
# =============================================================================

_token_blacklist: Set[str] = set()


def add_token_to_blacklist(token: str) -> None:
    """Add a token to the blacklist (logout)"""
    _token_blacklist.add(token)


def is_token_blacklisted(token: str) -> bool:
    """Check if a token is blacklisted"""
    return token in _token_blacklist


def clear_blacklist() -> None:
    """Clear all blacklisted tokens (for testing)"""
    _token_blacklist.clear()


# =============================================================================
# Password Functions (using bcrypt directly)
# =============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password"""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'), 
        hashed_password.encode('utf-8')
    )


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


# =============================================================================
# User Functions
# =============================================================================

def get_user(username: str) -> Optional[UserInDB]:
    """Get user from database (reads password hash dynamically from .env)"""
    users_db = get_users_db()  # Get fresh data with current password hash
    if username in users_db:
        user_dict = users_db[username]
        return UserInDB(**user_dict)
    return None


def authenticate_user(username: str, password: str) -> Union[UserInDB, bool]:
    """Authenticate user with username and password"""
    user = get_user(username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


# =============================================================================
# JWT Token Functions
# =============================================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + get_access_token_expire_delta()
    
    to_encode.update({
        "exp": expire,
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT refresh token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + get_refresh_token_expire_delta()
    
    to_encode.update({
        "exp": expire,
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate a JWT token"""
    try:
        # Check if token is blacklisted (logged out)
        if is_token_blacklisted(token):
            return None
            
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")
        token_version: str = str(payload.get("ver", "0"))
        current_version = str(get_auth_token_version())
        
        if username is None:
            return None

        if token_version != current_version:
            return None
            
        return TokenData(username=username, role=role, token_version=token_version)
    except JWTError:
        return None


def decode_refresh_token(token: str) -> Optional[TokenData]:
    """Decode and validate a refresh token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Check if it's a refresh token
        if payload.get("type") != "refresh":
            return None
            
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")
        token_version: str = str(payload.get("ver", "0"))
        current_version = str(get_auth_token_version())
        
        if username is None:
            return None

        if token_version != current_version:
            return None
            
        return TokenData(username=username, role=role, token_version=token_version)
    except JWTError:
        return None
