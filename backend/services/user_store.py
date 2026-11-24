"""
用户存储：ES 上的用户 CRUD + 索引自举 + 演示管理员播种。

设计要点（都踩过坑或认真想过，别跳着改）：

1. **用户名即 _id**。查用户是一次 GET（`es.get(index, id=username)`），
   不用 search；唯一性也不靠"先查后写"（有竞态）——
   写入时带 `op_type="create"`，ES 对已存在 _id 返回 409，
   这是存储层级别的原子保证。

2. **密码只存 bcrypt 哈希**，映射里 `index:false`（不进倒排、不被聚合），
   只能按 _id 整条取出。任何接口都不回密码字段（见 schemas/auth.py 的 UserPublic）。

3. **索引自举**：服务启动不依赖外部建索引脚本 ——
   `ensure_users_index()` 在第一次用到用户功能时自动建。
   users 是小索引（几十人），不值得为它接 run_index 的别名切换机制
   （那套是为了 movies/reviews 的零停机重建设计的）。

4. **种子管理员**：课程演示需要能直接登录的后台账号。
   `seed_demo_admin()` 只在索引里一个 admin 都没有时创建，
   口令从 .env 读（ADMIN_PASSWORD），默认值仅限本机开发。
"""
from __future__ import annotations

from datetime import datetime, timezone

from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ConflictError, NotFoundError

from common.settings import settings
from index.mappings import USERS_MAPPING

# 角色：与原系统一致的角色二分。写死两个字面量，不上 enum ——
# 这个项目里"多一个角色"的成本应该体现在改这一行，而不是改配置。
ROLE_ADMIN = "admin"
ROLE_USER = "user"


class UserError(Exception):
    """用户模块领域异常的基类（由 API 层翻成 HTTP 错误）。"""


class UsernameTaken(UserError):
    """用户名已被占用（ES create 冲突）。"""


class UserNotFound(UserError):
    """用户不存在。"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_view(doc: dict) -> dict:
    """把 ES 文档转成可对外的用户视图 —— **绝不外泄 password_hash**。"""
    return {
        "username": doc.get("username"),
        "role": doc.get("role", ROLE_USER),
        "nickname": doc.get("nickname") or doc.get("username"),
        "created_at": doc.get("created_at"),
    }


async def ensure_users_index(es: AsyncElasticsearch) -> None:
    """users 索引不存在就按 USERS_MAPPING 建好（幂等，可反复调）。"""
    if await es.indices.exists(index=settings.es_index_users):
        return
    await es.indices.create(index=settings.es_index_users, mappings=USERS_MAPPING)


async def create_user(
    es: AsyncElasticsearch,
    username: str,
    password_hash: str,
    role: str = ROLE_USER,
    nickname: str | None = None,
) -> dict:
    """建用户。用户名已存在时抛 UsernameTaken（依赖 ES 的 409，无竞态）。"""
    doc = {
        "username": username,
        "password_hash": password_hash,
        "role": role,
        "nickname": nickname or username,
        "created_at": _now_iso(),
    }
    try:
        await es.index(index=settings.es_index_users, id=username,
                       document=doc, op_type="create", refresh=True)
    except ConflictError as exc:
        raise UsernameTaken(username) from exc
    return doc


async def get_user(es: AsyncElasticsearch, username: str) -> dict | None:
    """按用户名取用户；不存在返回 None（不是异常——"查无此人"是正常路径）。"""
    try:
        resp = await es.get(index=settings.es_index_users, id=username)
    except NotFoundError:
        return None
    return resp["_source"]


async def update_password(es: AsyncElasticsearch, username: str, new_hash: str) -> None:
    doc = await get_user(es, username)
    if doc is None:
        raise UserNotFound(username)
    await es.update(index=settings.es_index_users, id=username,
                    doc={"password_hash": new_hash}, refresh=True)


async def update_nickname(es: AsyncElasticsearch, username: str, nickname: str) -> dict:
    """改昵称，返回更新后的公开视图。用户不存在抛 UserNotFound。

    走 es.update 的部分更新而不是整条 index：并发改昵称/改密码时
    不会互相覆盖（整条覆盖是经典的 lost-update）。
    更新后重新 get 一次而不是解析 update 响应 —— ES 各版本的 update
    响应结构有差异（有的不带 _source），多一次 GET 换确定性。
    """
    doc = await get_user(es, username)
    if doc is None:
        raise UserNotFound(username)
    await es.update(index=settings.es_index_users, id=username,
                    doc={"nickname": nickname}, refresh=True)
    return public_view(await get_user(es, username) or doc)


async def seed_demo_admin(es: AsyncElasticsearch, password_hash: str) -> dict | None:
    """播种演示管理员：仅当索引里没有任何 admin 时创建。

    返回新建的用户文档；已存在 admin（或建索引过程中并发建成）时返回 None。
    password_hash 必须是**已哈希**的口令（调用方用 auth.hash_password 处理），
    这里不认任何魔法字符串。
    """
    await ensure_users_index(es)
    resp = await es.search(
        index=settings.es_index_users,
        size=0,
        query={"term": {"role": ROLE_ADMIN}},
    )
    if int((resp["hits"]["total"] or {}).get("value") or 0) > 0:
        return None
    try:
        return await create_user(es, username="admin", password_hash=password_hash,
                                 role=ROLE_ADMIN, nickname="演示管理员")
    except UsernameTaken:
        return None
