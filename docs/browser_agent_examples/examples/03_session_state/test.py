"""03 离线检查：状态写入临时目录，不保留认证文件。"""

from run import offline_check


if __name__ == "__main__":
    # offline_check 内部启动本地 Chromium，并断言全新会话成功恢复登录状态。
    offline_check()
    print("03 PASS：登录状态保存与复用")
