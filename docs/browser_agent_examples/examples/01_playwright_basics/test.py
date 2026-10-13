"""01 离线检查：真实启动 Chromium，但不访问互联网。"""

from run import run_demo


def main() -> None:
    # 调用同一个演示入口，验证真实 Chromium 中的读取结果，而不是模拟 DOM。
    names = run_demo(headless=True)
    # 数量检查防止漏读，名称检查防止读取到无关的页面元素。
    assert len(names) == 6
    assert "AI 推理工作站" in names
    print("01 PASS：导航、定位器和文本读取")


if __name__ == "__main__":
    main()
