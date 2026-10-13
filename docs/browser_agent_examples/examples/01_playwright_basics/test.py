"""01 离线检查：真实启动 Chromium，但不访问互联网。"""

from run import run_demo


def main() -> None:
    names = run_demo(headless=True)
    assert len(names) == 6
    assert "AI 推理工作站" in names
    print("01 PASS：导航、定位器和文本读取")


if __name__ == "__main__":
    main()
