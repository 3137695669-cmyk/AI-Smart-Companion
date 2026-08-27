# -*- coding: utf-8 -*-
"""AI 智能伴侣 桌面启动器（可打包成 exe）。

双击运行后：定位项目根目录 → 用 .venv 里的 streamlit 启动应用
→ 等服务就绪后自动打开浏览器。关闭本窗口即停止应用。
"""

import os
import subprocess
import sys
import time
import urllib.request
import webbrowser


def project_root():
    # 打包成 exe 后，exe 所在目录即项目根目录；源码运行时用脚本所在目录
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main():
    root = project_root()
    app_script = os.path.join(root, "AI Smart Companion.py")
    python = os.path.join(root, ".venv", "Scripts", "python.exe")

    if not os.path.exists(app_script):
        print("错误：找不到主程序 AI Smart Companion.py。")
        print("请把本启动器放到项目根目录（与 AI Smart Companion.py 同级）。")
        input("按回车退出...")
        return 1
    if not os.path.exists(python):
        print("错误：找不到虚拟环境 .venv。")
        print("请先按《项目介绍与使用说明.txt》配置好依赖。")
        input("按回车退出...")
        return 1

    port = 8501
    url = f"http://127.0.0.1:{port}"

    print("=" * 56)
    print("  正在启动 AI 智能伴侣 ...")
    print(f"  应用入口：{url}")
    print("  关闭本窗口即可停止应用。")
    print("=" * 56)

    cmd = [
        python, "-m", "streamlit", "run", app_script,
        "--server.headless", "true",
        "--server.port", str(port),
    ]

    proc = subprocess.Popen(cmd, cwd=root)

    # 等服务就绪后自动打开浏览器（最多等 30 秒）
    for _ in range(30):
        if proc.poll() is not None:
            print("\n[错误] Streamlit 未能启动，请检查上方输出。")
            break
        try:
            urllib.request.urlopen(f"{url}/_stcore/health", timeout=1)
            webbrowser.open(url)
            break
        except Exception:
            time.sleep(1)

    if proc.poll() is not None:
        input("\n按回车退出...")
        return proc.returncode

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n正在停止 ...")
        proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
