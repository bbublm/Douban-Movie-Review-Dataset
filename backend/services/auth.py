"""
认证服务：密码哈希、JWT 签发/校验、当前用户依赖。

安全取舍（课程项目量级，写在这里备查）：

· **bcrypt 而非 MD5/SHA**：bcrypt 自带盐与慢哈希（cost=12），
  同一口令两次哈希结果不同（盐随机），彩虹表直接失效。
  cost=12 约 250ms/次，对登录接口是合理的防爆破成本。
· **JWT 无状态**：服务端不存会话，token 自带身份（sub/username/role）。
  代价是"登出"无法即时失效（只能等过期）—— 课程演示可接受，
  真上生产要加黑名单或换短时效 + refresh token。
· **密钥从 .env 读**：默认值是开发占位，.env.example 里有显式警告。
  HS256 是对称签名，泄露密钥 = 任何人可伪造任意身份。

`get_current_user` 是给路由用的 FastAPI 依赖：
    校验 Authorization: Bearer <token>，成功返回用户公开视图；
    任何一步失败都是 401（不区分"没带头"和"头是错的"——
    细分错误码是在帮攻击者做信息收集）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.services.user_store import (
    ROLE_ADMIN,
    UserNotFound,
    ensure_users_index,
    get_user,
    public_view,
)
from common.es_client import get_es
from common.settings import settings

# auto_error=False：自己抓"没带头"的情况，统一回 401 + WWW-Authenticate，
# 而不是 FastAPI 默认的 403（语义不对，401 才表示"需要身份"）。
_bearer = HTTPBearer(auto_error=False)

_CREDENTIALS_EXC = HTTPException(
    status_code=401,
    detail="未登录或登录已过期，请重新登录",
    headers={"WWW-Authenticate": "Bearer"},
)


class AuthError(Exception):
    """认证领域异常基类。"""


class InvalidCredentials(AuthError):
    """用户名或密码错误。"""


# ---------------- 密码 ----------------

def hash_password(plain: str) -> str:
    """明文 → bcrypt 哈希字符串（含盐，可直接存）。"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    """校验口令。哈希格式损坏时返回 False 而不是抛异常——
    坏数据不该把登录接口打成 500（那等于告诉攻击者"这人存在但数据坏了"）。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------- JWT ----------------

def create_access_token(username: str, role: str) -> str:
    """签发 token。sub=用户名（本项目的用户主键），带 role 免去二次查库。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """解析并校验 token。任何失败（过期/篡改/签名错）都抛 InvalidCredentials。"""
    try:
        return jwt.decode(token, settings.jwt_secret,
                          algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidCredentials(str(exc)) from exc


# ---------------- FastAPI 依赖 ----------------

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """解析 Bearer token → 用户公开视图（username/role/nickname/created_at）。

    用户被删但 token 未过期的情况：返回 401 而不是放行——
    无状态 token 的固有缺口，用"每次请求核对一次存在性"兜底
    （用户量小，这次查询的成本可以忽略）。
    """
    if credentials is None or not credentials.credentials:
        raise _CREDENTIALS_EXC
    try:
        payload = decode_token(credentials.credentials)
    except InvalidCredentials:
        raise _CREDENTIALS_EXC from None

    es = get_es()
    try:
        doc = await get_user(es, payload["sub"])
    except Exception:  # noqa: BLE001 —— ES 抖动时按未登录处理，不暴露内部错误
        raise _CREDENTIALS_EXC from None
    if doc is None:
        raise _CREDENTIALS_EXC

    user = public_view(doc)
    # token 里的 role 与库里的不一致（角色被改过）以库为准
    user["role"] = doc.get("role", user["role"])
    request.state.user = user
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """管理员守卫：路由加这个依赖即限 admin（原系统的角色二分在 API 层的落点）。"""
    if user.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def login_user(username: str, password: str) -> dict:
    """登录：校验口令 → 签发 token。用户名不存在与口令错误**同一报错**，
    防止账号枚举。"""
    es = get_es()
    doc = await get_user(es, username)
    if doc is None or not verify_password(password, doc.get("password_hash", "")):
        raise InvalidCredentials("用户名或密码错误")
    user = public_view(doc)
    return {"access_token": create_access_token(doc["username"], doc.get("role", "user")),
            "token_type": "bearer",
            "user": user}


async def register_user(username: str, password: str, nickname: str | None = None) -> dict:
    """注册：建 user 角色账号并直接签 token（少一次登录点击，演示更顺）。"""
    from backend.services.user_store import UsernameTaken, create_user

    es = get_es()
    await ensure_users_index(es)
    try:
        doc = await create_user(es, username=username,
                                password_hash=hash_password(password),
                                nickname=nickname)
    except UsernameTaken as exc:
        raise AuthError(f"用户名 {username} 已被占用") from exc
    return {"access_token": create_access_token(doc["username"], doc.get("role", "user")),
            "token_type": "bearer",
            "user": public_view(doc)}


async def change_password(username: str, old_password: str, new_password: str) -> None:
    """改密码：先验旧口令再写新哈希。旧口令错误抛 InvalidCredentials。"""
    from backend.services.user_store import update_password

    es = get_es()
    doc = await get_user(es, username)
    if doc is None:
        raise UserNotFound(username)
    if not verify_password(old_password, doc.get("password_hash", "")):
        raise InvalidCredentials("原密码不正确")
    await update_password(es, username, hash_password(new_password))


async def update_profile(username: str, nickname: str) -> dict:
    """更新昵称，返回更新后的公开视图。用户不存在抛 UserNotFound。"""
    from backend.services.user_store import update_nickname

    return await update_nickname(get_es(), username, nickname)
