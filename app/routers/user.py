from fastapi import APIRouter, Depends
from app.dependencies import get_current_active_user
from app.models import User

router = APIRouter(prefix="/me", tags=["User Profile"])


@router.get("")
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current user profile - Protected endpoint example
    Requires valid access token
    """
    return {
        "id": current_user.id,
        "name": current_user.name,
        "username": current_user.username,
        "role_id": current_user.role_id,
        "role_name": current_user.role.name if current_user.role else None,
        "is_active": current_user.is_active,
        "last_login": current_user.last_login,
        "created_at": current_user.created_at
    }
