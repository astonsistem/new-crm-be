from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from uuid import UUID
from typing import Optional
from app.database import get_db
from app.models import User, RefreshToken
from app.schemas import TokenResponse, RefreshTokenRequest, AccessTokenResponse
from app.utils.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.utils.recaptcha import verify_recaptcha
from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.auth")
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    recaptcha_token: Optional[str] = Header(None, alias="X-Recaptcha-Response"),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return access + refresh tokens."""

    if recaptcha_token and not await verify_recaptcha(recaptcha_token):
        logger.warning("reCAPTCHA verification failed for login attempt (username=%s).", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reCAPTCHA",
        )

    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password):
        logger.warning("Failed login attempt for username='%s'.", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning("Login attempt by inactive account username='%s'.", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role_id": str(user.role_id)}
    )
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    refresh_token_expires = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db.add(
        RefreshToken(
            user_id=user.id,
            token=refresh_token,
            expires_at=refresh_token_expires,
        )
    )
    user.last_login = datetime.utcnow()
    await db.commit()

    logger.info("User '%s' (id=%s) logged in successfully.", user.username, user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_access_token(
    refresh_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Issue a new access token given a valid refresh token."""

    payload = decode_token(refresh_data.refresh_token)

    if payload is None:
        logger.warning("Refresh token decode failed.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        logger.warning("Refresh endpoint called with non-refresh token type='%s'.", payload.get("type"))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == refresh_data.refresh_token,
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,
            RefreshToken.expires_at > datetime.utcnow(),
        )
    )
    db_refresh_token = result.scalar_one_or_none()

    if not db_refresh_token:
        logger.warning("Refresh token not found / revoked / expired for user_id=%s.", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        logger.warning("Refresh requested for missing/inactive user id=%s.", user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found or inactive",
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role_id": str(user.role_id)}
    )

    logger.info("Access token refreshed for user '%s' (id=%s).", user.username, user.id)

    return AccessTokenResponse(access_token=access_token, token_type="bearer")


@router.post("/logout")
async def logout(
    refresh_token: Optional[str] = Header(None, alias="X-Refresh-Token"),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the refresh token if provided, then confirm logout.
    Token is optional — clients that don't store refresh tokens can still call this.
    """
    if refresh_token:
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token == refresh_token)
        )
        db_token = result.scalar_one_or_none()
        if db_token:
            db_token.is_revoked = True
            await db.commit()
            logger.info("Refresh token revoked for user_id=%s.", db_token.user_id)
        else:
            logger.debug("Logout called with unknown/already-revoked refresh token.")
    else:
        logger.debug("Logout called without refresh token — session cleared client-side only.")

    return {"detail": "Logged out successfully"}
