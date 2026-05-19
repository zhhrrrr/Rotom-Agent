# 允许在类型标注中使用尚未定义的类名，或者让类型注解延迟解析
# 在较新 Python 中可以减少循环引用问题
from __future__ import annotations

import base64      # 用于 Base64 编码 / 解码，JWT 就是 Base64URL 格式
import hashlib     # 提供哈希算法，例如 sha256、pbkdf2_hmac
import hmac        # 提供 HMAC 签名与安全比较 compare_digest
import json        # 用于把 header / payload 转成 JSON
import os          # 用于生成随机 salt
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings


# JWT 使用的签名算法
# HS256 = HMAC + SHA256
JWT_ALGORITHM = "HS256"

# 密码哈希迭代次数
# PBKDF2 会重复计算很多轮，让暴力破解密码变慢
PASSWORD_HASH_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    """
    对用户明文密码做哈希处理。

    输入：
        password: 用户输入的明文密码

    输出：
        一个可以安全保存到数据库的密码哈希字符串

    返回格式：
        pbkdf2_sha256$迭代次数$salt$digest
    """

    # 生成 16 字节随机 salt
    # salt 的作用是：即使两个用户密码一样，最终哈希结果也不一样
    salt = os.urandom(16)

    # 使用 PBKDF2-HMAC-SHA256 对密码做慢哈希
    # 参数含义：
    # "sha256"                      使用 sha256 哈希算法
    # password.encode("utf-8")       把密码转成 bytes
    # salt                           随机盐
    # PASSWORD_HASH_ITERATIONS       迭代次数
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )

    # 把算法名、迭代次数、salt、digest 拼成一个字符串
    # salt 和 digest 是 bytes，不能直接存，所以先做 base64 编码
    return "$".join(
        [
            "pbkdf2_sha256",
            str(PASSWORD_HASH_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, hashed_password: str) -> bool:
    """
    验证用户输入的明文密码是否匹配数据库中保存的密码哈希。

    输入：
        password: 用户登录时输入的明文密码
        hashed_password: 数据库中保存的哈希字符串

    输出：
        True  密码正确
        False 密码错误
    """

    try:
        # 把数据库里的哈希字符串拆开
        #
        # 例如：
        # pbkdf2_sha256$210000$salt$digest
        #
        # split("$", 3) 最多切 3 次，得到 4 段
        algorithm, iterations, salt, expected_digest = hashed_password.split("$", 3)

        # 只接受当前系统支持的算法
        if algorithm != "pbkdf2_sha256":
            return False

        # 用用户输入的 password + 原来的 salt + 原来的 iterations
        # 重新计算一次 digest
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64decode(salt),
            int(iterations),
        )

        # 把重新计算出来的 digest 和数据库里的 expected_digest 做比较
        #
        # 不用 ==，而是用 hmac.compare_digest
        # 原因：compare_digest 可以减少计时攻击风险
        return hmac.compare_digest(_b64encode(digest), expected_digest)

    except (ValueError, TypeError):
        # 如果 hashed_password 格式不对、iterations 不能转 int 等，都返回 False
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """
    创建 JWT Access Token。

    输入：
        subject: token 主体，一般是 user_id
        expires_delta: token 有效期，如果不传，就使用 settings 里的默认分钟数

    输出：
        JWT 字符串：
        header.payload.signature
    """

    # 计算 token 过期时间
    expires_at = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )

    # JWT payload，也就是 token 里携带的数据
    payload = {
        # sub = subject，通常存用户 ID
        "sub": subject,

        # exp = expiration time，过期时间，Unix 时间戳
        "exp": int(expires_at.timestamp()),

        # iat = issued at，签发时间，Unix 时间戳
        "iat": int(datetime.now(UTC).timestamp()),
    }

    # JWT header，声明算法和类型
    header = {
        "alg": JWT_ALGORITHM,
        "typ": "JWT",
    }

    # 把 header 转成 JSON，再做 Base64URL 编码
    encoded_header = _json_b64encode(header)

    # 把 payload 转成 JSON，再做 Base64URL 编码
    encoded_payload = _json_b64encode(payload)

    # 对 header.payload 进行签名
    # JWT 签名对象就是：
    # base64url(header) + "." + base64url(payload)
    signature = _sign(f"{encoded_header}.{encoded_payload}")

    # 最终 JWT 格式：
    # header.payload.signature
    return f"{encoded_header}.{encoded_payload}.{signature}"


def decode_access_token(token: str) -> dict[str, Any]:
    """
    解码并验证 JWT Access Token。

    输入：
        token: 前端传来的 JWT 字符串

    输出：
        payload 字典

    如果 token 格式错误、签名错误、算法错误、过期，则抛 ValueError。
    """

    try:
        # JWT 标准格式是三段：
        # encoded_header.encoded_payload.signature
        encoded_header, encoded_payload, signature = token.split(".", 2)

    except ValueError as exc:
        # 如果不是三段，说明 token 格式不对
        raise ValueError("Invalid token format") from exc

    # 根据 header.payload 重新计算签名
    expected_signature = _sign(f"{encoded_header}.{encoded_payload}")

    # 比较客户端传来的 signature 和服务端重新计算的 signature
    # 如果不一致，说明 token 被篡改，或者 secret 不对
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid token signature")

    # 解码 header
    header = json.loads(_b64decode(encoded_header))

    # 检查算法是否是 HS256
    # 防止出现不支持的算法
    if header.get("alg") != JWT_ALGORITHM:
        raise ValueError("Unsupported token algorithm")

    # 解码 payload
    payload = json.loads(_b64decode(encoded_payload))

    # 取出 exp 过期时间
    expires_at = payload.get("exp")

    # exp 必须是 int 类型时间戳
    if not isinstance(expires_at, int):
        raise ValueError("Token missing exp")

    # 如果当前时间已经超过 exp，说明 token 过期
    if expires_at < int(datetime.now(UTC).timestamp()):
        raise ValueError("Token expired")

    # 验证通过，返回 payload
    return payload


def _sign(value: str) -> str:
    """
    对字符串进行 HMAC-SHA256 签名。

    输入：
        value: 通常是 encoded_header.encoded_payload

    输出：
        Base64URL 编码后的签名字符串
    """

    digest = hmac.new(
        # HMAC 的密钥，也就是你的 JWT_SECRET_KEY
        settings.jwt_secret_key.encode("utf-8"),

        # 要签名的数据
        value.encode("utf-8"),

        # 使用 sha256 哈希算法
        hashlib.sha256,
    ).digest()

    # JWT 签名部分也要用 Base64URL 编码
    return _b64encode(digest)


def _json_b64encode(value: dict[str, Any]) -> str:
    """
    把 dict 转成紧凑 JSON，再做 Base64URL 编码。

    例如：
        {"alg": "HS256", "typ": "JWT"}

    变成：
        eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
    """

    # separators=(",", ":") 去掉 JSON 中多余空格
    # sort_keys=True 保证 key 顺序稳定，方便签名结果稳定
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")

    return _b64encode(raw)


def _b64encode(value: bytes) -> str:
    """
    Base64URL 编码。

    JWT 使用的是 URL-safe Base64：
        + 变成 -
        / 变成 _

    并且 JWT 通常去掉末尾的 = padding。
    """

    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    """
    Base64URL 解码。

    因为编码时去掉了末尾的 =，
    解码前需要把 padding 补回来。
    """

    # 计算需要补几个 =
    padding = "=" * (-len(value) % 4)

    # 补齐 padding 后再解码
    return base64.urlsafe_b64decode(value + padding)