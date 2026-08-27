# -*- coding: utf-8 -*-
"""认证与加密：密码哈希（bcrypt）、API Key 加解密（Fernet）、注册/登录。"""

import base64
import hashlib

import bcrypt
import pymysql
from cryptography.fernet import Fernet

import config
import db


# ---------------- 密码哈希 ----------------

def hash_password(password):
    """返回 bcrypt 哈希（字符串）。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, hashed):
    """校验密码是否匹配。"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------- API Key 加解密 ----------------

def _get_fernet():
    """由 config.SECRET_KEY 派生一个 Fernet 密钥。"""
    digest = hashlib.sha256(config.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_key(plain):
    """加密 API Key，空值返回 None。"""
    if not plain:
        return None
    return _get_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_key(cipher):
    """解密 API Key，空值返回 None。"""
    if not cipher:
        return None
    return _get_fernet().decrypt(cipher.encode("utf-8")).decode("utf-8")


# ---------------- 注册 / 登录 ----------------

def is_valid_phone(phone):
    """仅做格式校验（不发送验证码）：6~20 位数字，允许 + - 空格。"""
    p = (phone or "").replace("+", "").replace("-", "").replace(" ", "")
    return p.isdigit() and 6 <= len(p) <= 20


def register(phone, password, username=None, api_key=None):
    """注册新用户，成功返回用户 dict；失败抛 ValueError。"""
    phone = (phone or "").strip()
    username = (username or "").strip() or None
    if not phone or not password:
        raise ValueError("手机号和密码不能为空")
    if not is_valid_phone(phone):
        raise ValueError("手机号格式不正确")

    try:
        user_id = db.create_user(
            phone, hash_password(password), username, encrypt_key(api_key)
        )
    except pymysql.err.IntegrityError as e:
        if "uq_phone" in str(e):
            raise ValueError("该手机号已被注册")
        raise ValueError("注册失败，请稍后重试")

    return {
        "id": user_id,
        "phone": phone,
        "username": username,
        "api_key": (api_key or None),
    }


def login(phone, password):
    """登录，成功返回用户 dict（含解密后的 api_key 和显示名）；失败返回 None。"""
    user = db.get_user_by_phone((phone or "").strip())
    if user is None:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return {
        "id": user["id"],
        "phone": user["phone"],
        "username": user["username"],
        "api_key": decrypt_key(user["api_key_encrypted"]),
    }
