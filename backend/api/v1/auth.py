"""
用户认证接口：注册 / 登录 / 我的信息 / 改密码 / 改昵称。

| 接口 | 用途 |
|---|---|
| `POST /api/v1/auth/register` | 注册（自动登录，直接返回 token） |
| `POST /api/v1/auth/login` | 登录 |
| `GET  /api/v1/auth/me` | 当前登录用户（Bearer token） |
| `PATCH /api/v1/auth/me` | 更新个人资料（目前仅昵称） |
| `POST /api/v1/auth/change-password` | 修改密码（需登录 + 旧口令） |

角色模型与原系统一致（admin/user）。本文件只管"身份"，
行为数据（评分/观看记录）在 ratings 模块，想看清单在 watchlist 模块，
推荐消费它们。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserPublic,
)
from backend.services.auth import (
    AuthError,
    InvalidCredentials,
    change_password as _change_password,
    get_current_user,
    login_user,
    register_user,
    update_profile,
)
from backend.services.user_store import UserNotFound

router = APIRouter()


@router.post("/register", response_model=TokenResponse, summary="注册（自动登录）")
async def register(req: RegisterRequest) -> TokenResponse:
    try:
        return TokenResponse(**await register_user(req.username, req.password, req.nickname))
    except AuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/login", response_model=TokenResponse, summary="登录")
async def login(req: LoginRequest) -> TokenResponse:
    try:
        return TokenResponse(**await login_user(req.username, req.password))
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail="用户名或密码错误") from exc


@router.get("/me", response_model=UserPublic, summary="当前登录用户")
async def me(user: dict = Depends(get_current_user)) -> UserPublic:
    return UserPublic(**user)


@router.patch("/me", response_model=UserPublic, summary="更新个人资料（昵称）")
async def patch_me(req: UpdateProfileRequest,
                   user: dict = Depends(get_current_user)) -> UserPublic:
    """改昵称。用户名是主键不给改；角色只能后台改（防自助提权）。"""
    try:
        updated = await update_profile(user["username"], req.nickname)
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return UserPublic(**updated)


@router.post("/change-password", summary="修改密码")
async def change_password(
    req: ChangePasswordRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        await _change_password(user["username"], req.old_password, req.new_password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=400, detail="原密码不正确") from exc
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"message": "密码已修改，请重新登录"}
