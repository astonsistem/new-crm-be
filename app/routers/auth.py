from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import get_db
from app.models import User, RefreshToken
from app.schemas import LoginRequest, TokenResponse, RefreshTokenRequest, AccessTokenResponse
from app.utils.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Login endpoint - returns access token and refresh token
    """
    # Find user by username
    user = db.query(User).filter(User.username == login_data.username).first()
    
    if not user or not verify_password(login_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )
    
    # Create access token
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role_id": user.role_id}
    )
    
    # Create refresh token
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )
    
    # Store refresh token in database
    refresh_token_expires = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=refresh_token_expires
    )
    db.add(db_refresh_token)
    
    # Update last login
    user.last_login = datetime.utcnow()
    
    db.commit()
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_access_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token
    """
    # Decode refresh token
    payload = decode_token(refresh_data.refresh_token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token - cannot decode"
        )
    
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token - wrong type"
        )
    
    user_id_str = payload.get("sub")
    
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token - no user id"
        )
    
    # Convert user_id from string to int
    user_id = int(user_id_str)
    
    # Check if refresh token exists in database and is valid
    db_refresh_token = db.query(RefreshToken).filter(
        RefreshToken.token == refresh_data.refresh_token,
        RefreshToken.user_id == user_id,
        RefreshToken.is_revoked == False,
        RefreshToken.expires_at > datetime.utcnow()
    ).first()
    
    if not db_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found or inactive"
        )
    
    # Create new access token
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role_id": user.role_id}
    )
    
    return AccessTokenResponse(
        access_token=access_token,
        token_type="bearer"
    )


@router.post("/logout")
async def logout(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Logout endpoint - revokes refresh token
    """
    # Find and revoke refresh token
    db_refresh_token = db.query(RefreshToken).filter(
        RefreshToken.token == refresh_data.refresh_token
    ).first()
    
    if db_refresh_token:
        db_refresh_token.is_revoked = True
        db.commit()
    
    return {"message": "Successfully logged out"}
