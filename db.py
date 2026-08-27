# -*- coding: utf-8 -*-
"""MySQL 数据访问层：连接、自动建库建表、用户/会话/消息的 CRUD。"""

import pymysql
from pymysql.cursors import DictCursor

import config

_PLACEHOLDER_PASSWORD = "在这里填你的 MySQL root 密码"


def _check_config():
    """防止用户忘了填 config.py 里的 root 密码。"""
    if config.DB_PASSWORD == _PLACEHOLDER_PASSWORD:
        raise RuntimeError(
            "请先打开 config.py，把 DB_PASSWORD 改成你自己的 MySQL root 密码再运行。"
        )


def get_connection(database=config.DB_NAME):
    """返回一个 MySQL 连接。默认连业务库 config.DB_NAME；传 None 表示不指定库。"""
    _check_config()
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


def init_db():
    """首次启动时自动创建数据库和三张表（幂等，可重复调用）。"""
    _check_config()

    # 1) 先连到系统库，确保业务库存在
    conn = get_connection(database=None)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()

    # 2) 再连业务库建表
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    phone VARCHAR(20) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    username VARCHAR(50) NULL,
                    api_key_encrypted TEXT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_phone (phone)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    session_name VARCHAR(255) NOT NULL,
                    personality VARCHAR(255) DEFAULT '温柔可爱的小女生',
                    nick_name VARCHAR(255) DEFAULT '小可爱',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_user_session (user_id, session_name),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id INT NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

        # 3) 迁移：把旧 users 表升级到「手机号登录」结构（幂等）
        with conn.cursor() as cur:
            # 3.1 确保有 phone 列
            cur.execute(
                "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='users' AND COLUMN_NAME='phone'",
                (config.DB_NAME,),
            )
            if cur.fetchone()["c"] == 0:
                cur.execute("ALTER TABLE users ADD COLUMN phone VARCHAR(20) NULL")

            # 3.2 去掉 username 的唯一约束（用户名降级为可重复的显示名）
            cur.execute(
                "SELECT COUNT(*) AS c FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='users' AND INDEX_NAME='username'",
                (config.DB_NAME,),
            )
            if cur.fetchone()["c"] > 0:
                cur.execute("ALTER TABLE users DROP INDEX username")

            # 3.3 显示名允许为空
            cur.execute("ALTER TABLE users MODIFY username VARCHAR(50) NULL")

            # 3.4 手机号成为必填 + 唯一的登录标识
            cur.execute("ALTER TABLE users MODIFY phone VARCHAR(20) NOT NULL")
            cur.execute(
                "SELECT COUNT(*) AS c FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='users' AND INDEX_NAME='uq_phone'",
                (config.DB_NAME,),
            )
            if cur.fetchone()["c"] == 0:
                cur.execute("ALTER TABLE users ADD UNIQUE KEY uq_phone (phone)")
    finally:
        conn.close()


# ---------------- 用户 ----------------

def create_user(phone, password_hash, username=None, api_key_encrypted=None):
    """新建用户，返回新用户 id。手机号重复时抛 pymysql.IntegrityError。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (phone, password_hash, username, api_key_encrypted) "
                "VALUES (%s, %s, %s, %s)",
                (phone, password_hash, username, api_key_encrypted),
            )
            return cur.lastrowid
    finally:
        conn.close()


def get_user_by_phone(phone):
    """按手机号查用户，返回 dict 或 None。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, phone, password_hash, username, api_key_encrypted "
                "FROM users WHERE phone = %s",
                (phone,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def update_user_display_name(user_id, username):
    """更新用户显示名（可重复；传 None 表示清空）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET username = %s WHERE id = %s",
                (username, user_id),
            )
    finally:
        conn.close()


def update_user_api_key(user_id, api_key_encrypted):
    """更新用户的 API Key（加密后的密文）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET api_key_encrypted = %s WHERE id = %s",
                (api_key_encrypted, user_id),
            )
    finally:
        conn.close()


# ---------------- 会话 ----------------

def upsert_session(user_id, session_name, personality, nick_name):
    """新建或更新会话，返回 session_id。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (user_id, session_name, personality, nick_name)
                VALUES (%s, %s, %s, %s) AS new
                ON DUPLICATE KEY UPDATE
                    personality = new.personality,
                    nick_name = new.nick_name
                """,
                (user_id, session_name, personality, nick_name),
            )
            cur.execute(
                "SELECT id FROM sessions WHERE user_id = %s AND session_name = %s",
                (user_id, session_name),
            )
            return cur.fetchone()["id"]
    finally:
        conn.close()


def get_session(user_id, session_name):
    """按会话名查某个用户的会话，返回 dict 或 None。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, session_name, personality, nick_name "
                "FROM sessions WHERE user_id = %s AND session_name = %s",
                (user_id, session_name),
            )
            return cur.fetchone()
    finally:
        conn.close()


def list_sessions(user_id):
    """返回某用户的所有会话（按创建时间倒序）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_name, personality, nick_name, created_at "
                "FROM sessions WHERE user_id = %s ORDER BY created_at DESC, id DESC",
                (user_id,),
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def delete_session(user_id, session_name):
    """删除某用户的一个会话（消息级联删除）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sessions WHERE user_id = %s AND session_name = %s",
                (user_id, session_name),
            )
    finally:
        conn.close()


# ---------------- 消息 ----------------

def append_message(session_id, role, content):
    """往某个会话追加一条消息。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
                (session_id, role, content),
            )
    finally:
        conn.close()


def list_messages(session_id):
    """按发送顺序返回某个会话的全部消息。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM messages "
                "WHERE session_id = %s ORDER BY id ASC",
                (session_id,),
            )
            return list(cur.fetchall())
    finally:
        conn.close()
