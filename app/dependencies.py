from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.database import get_db
from app.models import User
from app.utils.security import decode_token
from app.utils.eager_loads import user_joinedload_options
from app.core.logging import get_logger

logger = get_logger("app.auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode JWT access token and return the authenticated User."""
    payload = decode_token(token)

    if payload is None:
        logger.warning("Token decode failed — invalid or expired token.")
        raise _CREDENTIALS_EXCEPTION

    if payload.get("type") != "access":
        logger.warning("Token type mismatch: expected 'access', got '%s'.", payload.get("type"))
        raise _CREDENTIALS_EXCEPTION

    user_id_str: str = payload.get("sub")
    if not user_id_str:
        logger.warning("Token is missing 'sub' claim.")
        raise _CREDENTIALS_EXCEPTION

    try:
        user_id = UUID(user_id_str)
    except (ValueError, AttributeError):
        logger.warning("Token 'sub' claim is not a valid UUID: %s", user_id_str)
        raise _CREDENTIALS_EXCEPTION

    result = await db.execute(
        select(User)
        .options(*user_joinedload_options())
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning("Authenticated user not found in DB (id=%s).", user_id)
        raise _CREDENTIALS_EXCEPTION

    if not user.is_active:
        logger.warning("Login attempt by inactive user '%s' (id=%s).", user.username, user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Alias kept for backward compatibility — returns the authenticated user."""
    return current_user
