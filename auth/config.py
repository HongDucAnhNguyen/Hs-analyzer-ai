"""Authentication configuration

Contains JWT settings, secret key, and user credentials from environment.
Supports dynamic password hash reloading from .env file for password rotation.
"""

import os
import re
from datetime import timedelta
from pathlib import Path

# =============================================================================
# JWT Configuration
# =============================================================================

SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", 
    "your-super-secret-key-change-this-in-production-hs-code-api-2024"
)

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# =============================================================================
# User Credentials from Environment
# =============================================================================

AUTH_USERNAME = os.getenv("AUTH_USERNAME", "")
AUTH_TOKEN_VERSION = os.getenv("AUTH_TOKEN_VERSION", "0")

# Path to .env file for dynamic password hash reading
ENV_FILE_PATH = Path("/app/.env")


def get_password_hash_from_env_file() -> str:
    """
    Read AUTH_PASSWORD_HASH directly from .env file.
    This allows password rotation without container restart.
    """
    try:
        if ENV_FILE_PATH.exists():
            content = ENV_FILE_PATH.read_text()
            match = re.search(r'AUTH_PASSWORD_HASH=(.+?)(?:\n|$)', content)
            if match:
                return match.group(1).strip()
    except Exception:
        pass
    
    # Fallback to environment variable
    return os.getenv("AUTH_PASSWORD_HASH", "")


def get_token_version_from_env_file() -> str:
    """
    Read AUTH_TOKEN_VERSION directly from .env file.
    This allows global token invalidation without container restart.
    """
    try:
        if ENV_FILE_PATH.exists():
            content = ENV_FILE_PATH.read_text()
            match = re.search(r'AUTH_TOKEN_VERSION=(.+?)(?:\n|$)', content)
            if match:
                return match.group(1).strip()
    except Exception:
        pass

    # Fallback to environment variable
    return os.getenv("AUTH_TOKEN_VERSION", "0")


def get_auth_token_version() -> str:
    """Get current auth token version."""
    return get_token_version_from_env_file()


def get_users_db() -> dict:
    """
    Get users database with current password hash.
    Reads password hash dynamically from .env file to support password rotation.
    """
    username = AUTH_USERNAME
    password_hash = get_password_hash_from_env_file()
    
    if username and password_hash:
        return {
            username: {
                "username": username,
                "email": f"{username}@ey.com",
                "full_name": "EY Global Trade Staff",
                "hashed_password": password_hash,
                "disabled": False,
                "role": "admin"
            }
        }
    return {}


# For backwards compatibility - but prefer using get_users_db()
USERS_DB = get_users_db()

# =============================================================================
# Helper Functions
# =============================================================================

def get_access_token_expire_delta() -> timedelta:
    """Get access token expiration timedelta"""
    return timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

def get_refresh_token_expire_delta() -> timedelta:
    """Get refresh token expiration timedelta"""
    return timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
