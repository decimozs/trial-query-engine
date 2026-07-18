from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_user, require_admin
from app.models import User
from app.schemas.user import UserOut


router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/admin/check")
async def admin_check(_: User = Depends(require_admin)) -> dict[str, bool]:
    return {"ok": True}
