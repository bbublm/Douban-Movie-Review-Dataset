"""用户模块实测脚本：注册/登录/me/改密/权限 全流程（一次性验证用，不入库）。

每次运行用带时间戳的用户名，可重复执行不冲突。
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000/api/v1/auth"
SUFFIX = str(int(time.time()))[-6:]
USER = f"alice_{SUFFIX}"
PWD = "secret1"


def call(method: str, path: str, body: dict | None = None, token: str | None = None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw.decode("utf-8", "replace")[:200]}
    except urllib.error.URLError as e:
        return 0, {"error": str(e)}


print(f"== 1. 注册新用户 {USER} ==")
s, r = call("POST", "/register", {"username": USER, "password": PWD, "nickname": "Alice"})
print(s, "user:", json.dumps(r.get("user"), ensure_ascii=False))
token = r.get("access_token", "")

print("\n== 2. 重复注册同一用户名（应 409）==")
s, r = call("POST", "/register", {"username": USER, "password": PWD})
print(s, json.dumps(r, ensure_ascii=False)[:100])

print("\n== 3. 错误口令登录（应 401）==")
s, r = call("POST", "/login", {"username": USER, "password": "wrong"})
print(s, json.dumps(r, ensure_ascii=False)[:100])

print("\n== 4. 不存在用户登录（应 401，防账号枚举）==")
s, r = call("POST", "/login", {"username": "nobody_here", "password": PWD})
print(s, json.dumps(r, ensure_ascii=False)[:100])

print("\n== 5. 正确登录（token 从这里取）==")
s, r = call("POST", "/login", {"username": USER, "password": PWD})
print(s, "role:", (r.get("user") or {}).get("role"))
token = r.get("access_token", "")

print("\n== 6. 带 token 取 /me（应 200）==")
s, r = call("GET", "/me", token=token)
print(s, json.dumps(r, ensure_ascii=False))

print("\n== 7. 无 token / 假 token 取 /me（应 401）==")
s, r = call("GET", "/me")
print("无 token:", s)
s, r = call("GET", "/me", token="fake.token.here")
print("假 token:", s)

print("\n== 8. 演示管理员登录（启动时自动播种）==")
s, r = call("POST", "/login", {"username": "admin", "password": "admin123"})
print(s, "role:", (r.get("user") or {}).get("role"), "nickname:", (r.get("user") or {}).get("nickname"))

print("\n== 9. 修改密码（旧口令错 → 400；正确 → 200）==")
s, r = call("POST", "/change-password", {"old_password": "bad-old", "new_password": "newpass1"}, token=token)
print("错误旧口令:", s, json.dumps(r, ensure_ascii=False)[:80])
s, r = call("POST", "/change-password", {"old_password": PWD, "new_password": "newpass1"}, token=token)
print("正确修改:", s, json.dumps(r, ensure_ascii=False)[:80])

print("\n== 10. 改密后旧口令登录（应 401），新口令登录（应 200）==")
s, r = call("POST", "/login", {"username": USER, "password": PWD})
print("旧口令:", s)
s, r = call("POST", "/login", {"username": USER, "password": "newpass1"})
print("新口令:", s)

print("\n== 11. 非法注册载荷（应 422）==")
for bad in [{"username": "ab", "password": "secret1"},
            {"username": "中文名", "password": "secret1"},
            {"username": "alice2", "password": "123"}]:
    s, r = call("POST", "/register", bad)
    print(f"{bad['username']}/{bad['password']} ->", s)

print("\n== 12. 已删除用户 + 未过期 token（应 401，按未登录处理）==")
# 不真实删用户（ES delete 需要额外接口），只验证伪造 sub 的 token 会被拒：
# get_current_user 会拿 token 里的 sub 去查库，查无此人 → 401
import jwt as pyjwt
from datetime import datetime, timedelta, timezone
from common.settings import settings

ghost = pyjwt.encode(
    {"sub": "ghost_user", "role": "admin",
     "iat": datetime.now(timezone.utc), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
    settings.jwt_secret, algorithm="HS256")
s, r = call("GET", "/me", token=ghost)
print("库里不存在的 sub:", s, json.dumps(r, ensure_ascii=False)[:80])
