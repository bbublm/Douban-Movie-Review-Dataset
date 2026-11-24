"""
用户认证接口的请求 / 响应模型。

★ UserPublic 是唯一能对外的用户形状：**没有 password_hash 字段**。
   把 ES 文档直接塞进响应模型是泄密事故的经典源头 ——
   加字段时忘删 password_hash，接口就把哈希给出去了。
   所以对外视图只认这一个模型，别处不许手拼字典。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """注册请求。用户名/口令规则在这里集中校验，路由不重复判断。"""

    username: str = Field(..., min_length=3, max_length=32,
                          pattern=r"^[a-zA-Z0-9_]+$",
                          description="3-32 位字母/数字/下划线")
    password: str = Field(..., min_length=6, max_length=64,
                          description="至少 6 位")
    nickname: str | None = Field(default=None, max_length=32)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=64)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=64)
    new_password: str = Field(..., min_length=6, max_length=64)


class UpdateProfileRequest(BaseModel):
    """更新个人资料。目前只开放昵称 —— 用户名是主键（_id）不给改，
    角色只能由管理员在后台改（开放自助提权等于没有权限体系）。"""

    nickname: str = Field(..., min_length=1, max_length=32, description="展示名，1-32 字符")


class UserPublic(BaseModel):
    """用户公开视图。role 供前端做权限渲染（如管理入口显隐）。"""

    username: str
    role: str = "user"
    nickname: str = ""
    created_at: str | None = None


class TokenResponse(BaseModel):
    """登录/注册成功后的令牌 + 用户信息（省前端再查一次 /me）。"""

    access_token: str
    token_type: str = "bearer"
    user: UserPublic
