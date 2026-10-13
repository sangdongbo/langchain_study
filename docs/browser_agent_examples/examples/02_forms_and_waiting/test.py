"""02 离线检查：表单交互和基于状态的等待。"""

from run import run_demo


def main() -> None:
    # 工作站超预算，迷你主机不含 32GB；三项条件共同作用后只剩笔记本。
    assert run_demo(headless=True) == ["数据分析笔记本"]
    print("02 PASS：表单、点击、自动等待和断言")


if __name__ == "__main__":
    main()
