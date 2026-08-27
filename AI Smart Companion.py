import streamlit as st
import datetime
from openai import OpenAI

import db
import auth

st.set_page_config(
    page_title="AI智能伴侣 App",
    page_icon="💕",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.extremelycoolapp.com/help',
        'Report a bug': "https://www.extremelycoolapp.com/bug",
        'About': "# This is a header. This is an *extremely* cool app!"
    }
)

# 首次启动：自动建库建表（幂等）
try:
    db.init_db()
except RuntimeError as e:
    st.error(str(e))
    st.stop()
except Exception as e:
    st.error(f"数据库连接失败，请检查 config.py 里的 MySQL 配置是否正确。\n\n详情：{e}")
    st.stop()

# ---------------- 登录态初始化 ----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "username" not in st.session_state:
    st.session_state.username = None
if "api_key" not in st.session_state:
    st.session_state.api_key = None
if "phone" not in st.session_state:
    st.session_state.phone = None


def _set_login_state(user):
    """登录/注册成功后写入会话状态。"""
    st.session_state.logged_in = True
    st.session_state.user_id = user["id"]
    st.session_state.username = user["username"]
    st.session_state.api_key = user["api_key"]
    st.session_state.phone = user.get("phone")
    # 清空上一任用户的聊天状态，避免串号
    for key in ["messages", "session_name", "nick_name", "Personality"]:
        st.session_state.pop(key, None)


def _clear_login_state():
    """退出登录：清空所有与会话相关的状态。"""
    for key in ["logged_in", "user_id", "username", "api_key", "phone",
                "messages", "session_name", "nick_name", "Personality"]:
        st.session_state.pop(key, None)


# ---------------- 未登录：登录 / 注册页 ----------------
if not st.session_state.logged_in:
    st.title("💕 AI智能伴侣")
    st.caption("请先登录或注册。每个用户使用自己的 DeepSeek API Key，历史记录保存在数据库中。")

    tab_login, tab_register = st.tabs(["登录", "注册"])

    with tab_login:
        with st.form("login_form"):
            phone = st.text_input("手机号")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", use_container_width=True)
            if submitted:
                user = auth.login(phone, password)
                if user:
                    _set_login_state(user)
                    st.rerun()
                else:
                    st.error("手机号或密码错误")

    with tab_register:
        with st.form("register_form"):
            phone = st.text_input("手机号（登录账号，必填）")
            password = st.text_input("密码", type="password")
            username = st.text_input("显示名（可选，可重复）")
            api_key = st.text_input("DeepSeek API Key（可选，之后也能补填）", type="password")
            submitted = st.form_submit_button("注册", use_container_width=True)
            if submitted:
                try:
                    user = auth.register(phone, password, username, api_key)
                except ValueError as e:
                    st.error(str(e))
                else:
                    _set_login_state(user)
                    st.rerun()

    st.stop()

# ================= 已登录：主界面 =================

# 生成会话名字
def generate_session_name():
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


# 保存当前会话元信息（昵称/性格）；消息在聊天时已实时入库，这里只做 upsert 元信息
def save_session_info():
    # 只有消息不为空时才保存，避免生成空会话
    if st.session_state.session_name and st.session_state.messages:
        db.upsert_session(
            st.session_state.user_id,
            st.session_state.session_name,
            st.session_state.Personality,
            st.session_state.nick_name,
        )


# 加载当前用户的所有会话列表
def load_session_list():
    return db.list_sessions(st.session_state.user_id)


# 大标题
st.title("AI智能伴侣")
"""
AI智能伴侣，基于 DeepSeek 大模型，实现对用户输入的问题的回答。
"""
# logo
st.logo("伴侣logo.png")

# 初始化聊天信息（必须在侧边栏之前，否则 text_input 拿不到值）
if "messages" not in st.session_state:
    st.session_state.messages = []

# 昵称
if "nick_name" not in st.session_state:
    st.session_state.nick_name = "小可爱"

# 性格
if "Personality" not in st.session_state:
    st.session_state.Personality = "温柔可爱的小女生"

# 会话名字
if "session_name" not in st.session_state:
    st.session_state.session_name = generate_session_name()

# 未设置 API Key 时给出提示
if not st.session_state.api_key:
    st.warning("⚠️ 你还没有设置 DeepSeek API Key，请到左侧「API Key 设置」里填写后即可聊天。")

# 侧边栏
with st.sidebar:
    st.header("控制面板")

    # 当前用户 + 退出登录
    display_name = st.session_state.username or "未设置显示名"
    st.caption(f"当前账号：{st.session_state.phone}（{display_name}）")
    if st.button("退出登录", use_container_width=True, icon="🚪"):
        _clear_login_state()
        st.rerun()

    st.divider()

    # API Key 设置
    with st.expander("API Key 设置"):
        new_key = st.text_input(
            "DeepSeek API Key",
            value=st.session_state.api_key or "",
            type="password",
            placeholder="sk-...",
        )
        if st.button("保存 API Key", use_container_width=True):
            new_key = (new_key or "").strip()
            if new_key:
                db.update_user_api_key(st.session_state.user_id, auth.encrypt_key(new_key))
                st.session_state.api_key = new_key
                st.success("已保存 ✅")
                st.rerun()
            else:
                st.warning("请输入 key")

    # 显示名设置
    with st.expander("显示名设置"):
        new_name = st.text_input(
            "显示名",
            value=st.session_state.username or "",
            placeholder="可选，可重复",
        )
        if st.button("保存显示名", use_container_width=True):
            new_name = (new_name or "").strip() or None
            db.update_user_display_name(st.session_state.user_id, new_name)
            st.session_state.username = new_name
            st.success("已保存 ✅")
            st.rerun()

    st.divider()

    # 会话信息
    st.subheader("会话信息")
    # 新建会话按钮
    if st.button("新建会话", use_container_width=True, icon="💌"):
        # 保存当前会话元信息
        save_session_info()
        # 创建新会话：始终生成新名字、清空消息
        st.session_state.messages = []
        st.session_state.session_name = generate_session_name()
        st.rerun()

    # 历史会话
    st.text("历史会话")
    session_list = load_session_list()
    for session in session_list:
        session_name = session["session_name"]
        col1, col2 = st.columns([4, 1])
        with col1:
            if st.button(session_name, use_container_width=True, icon="📃",
                         type="primary" if session_name == st.session_state.session_name else "tertiary"):
                # 先保存当前会话元信息，再加载历史会话
                save_session_info()
                sess = db.get_session(st.session_state.user_id, session_name)
                if sess:
                    st.session_state.messages = db.list_messages(sess["id"])
                    st.session_state.session_name = session_name
                    st.session_state.Personality = sess["personality"]
                    st.session_state.nick_name = sess["nick_name"]
                st.rerun()

        with col2:
            if st.button("", use_container_width=True, icon="🗑️", key=f"delete_{session_name}"):
                db.delete_session(st.session_state.user_id, session_name)
                # 如果删除的是当前会话，清空状态并生成新会话名
                if session_name == st.session_state.session_name:
                    st.session_state.messages = []
                    st.session_state.session_name = generate_session_name()
                st.rerun()

    # 分割线
    st.divider()

    # 伴侣信息
    st.text("伴侣信息")

    # 昵称输入框
    nick_name = st.text_input(
        "昵称",
        value=st.session_state.nick_name,
        placeholder="请输入昵称",
        key=f"nick_{st.session_state.session_name}"  # 绑定会话名，切换时刷新输入框
    )
    if nick_name:
        st.session_state.nick_name = nick_name

    # 性格输入框
    Personality = st.text_input(
        "性格",
        value=st.session_state.Personality,
        placeholder="请输入性格",
        key=f"personality_{st.session_state.session_name}"  # 绑定会话名，切换时刷新输入框
    )
    if Personality:
        st.session_state.Personality = Personality

# 展示历史聊天记录
for message in st.session_state.messages:
    if message["role"] == "user":
        st.chat_message("user").write(message["content"])
    else:
        st.chat_message("assistant").write(message["content"])

# 输入框
prompt = st.chat_input("请输入你的问题")
if prompt:
    if not st.session_state.api_key:
        st.warning("⚠️ 请先在左侧「API Key 设置」里填写你的 DeepSeek API Key")
    else:
        st.chat_message("user").write(f"用户: {prompt}")
        print("-------->调用AI大模型，提示词：", prompt)

        # 确保会话已入库，拿到 session_id 用于保存消息
        session_id = db.upsert_session(
            st.session_state.user_id,
            st.session_state.session_name,
            st.session_state.Personality,
            st.session_state.nick_name,
        )

        # 保存用户输入的提示词（内存 + 数据库）
        st.session_state.messages.append({"role": "user", "content": prompt})
        db.append_message(session_id, "user", prompt)

        # 系统提示词
        system_propemt = (f"""
        你是一个可以照顾用户情绪的，作为一个聊天式的用户情侣的身份，你的名字是{st.session_state.nick_name}
                          你要遵守以下规则：1.以微信聊天的方式去与用户进行聊天
                          2.可以多用emoji这种表情穿插在句子中，要合适
                          3.回答尽量简短，最好就几句话
                          4.如果用户输入的句子中包含敏感词，用委婉的方式拒绝
                          5.你的性格是{st.session_state.Personality}
        """
                          )

        # 调用 ai 大模型
        client = OpenAI(
            api_key=st.session_state.api_key,
            base_url="https://api.deepseek.com")

        # 调用AI大模型（流式）
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": system_propemt},
                *st.session_state.messages
            ],
            stream=True,  # 开启流式输出
            extra_body={"thinking": {"type": "enabled"}}
        )

        # 流式输出到界面，同时收集完整响应
        full_response = ""
        with st.chat_message("assistant"):
            message_placeholder = st.empty()  # 占位符，用于逐块更新
            for chunk in response:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.write(full_response)  # 实时更新
        print("大模型调用返回结果", full_response)

        # 保存大模型返回结果（内存 + 数据库）
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        db.append_message(session_id, "assistant", full_response)
