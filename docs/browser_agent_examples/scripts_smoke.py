"""不启动浏览器、不调用模型的项目静态自检。"""

import ast
from html.parser import HTMLParser
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


class TestIdParser(HTMLParser):
    # 只收集 HTML 里的稳定测试定位标记，不执行页面 JavaScript。
    def __init__(self) -> None:
        super().__init__()
        self.test_ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # HTMLParser 逐个通知开始标签，从其属性中提取 data-testid。
        for name, value in attrs:
            if name == "data-testid" and value:
                self.test_ids.add(value)


def main() -> None:
    # ast.parse 只检查语法，不导入示例，也不启动浏览器或请求模型。
    for directory in (PROJECT_DIR / "browser_examples", PROJECT_DIR / "examples"):
        for path in directory.rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    # 检查 02 使用的定位标记，提前发现页面与示例代码之间的命名不一致。
    parser = TestIdParser()
    parser.feed((PROJECT_DIR / "demo_site" / "index.html").read_text(encoding="utf-8"))
    assert {"keyword", "category", "max-price", "apply-filter", "result-status"} <= parser.test_ids
    assert (PROJECT_DIR / "demo_site" / "login.html").is_file()
    assert (PROJECT_DIR / "demo_site" / "dashboard.html").is_file()
    assert (PROJECT_DIR / "demo_site" / "detail.html").is_file()
    # 每个专题都必须有说明文档、可运行入口和检查脚本。
    for number in range(1, 6):
        matches = list((PROJECT_DIR / "examples").glob(f"{number:02d}_*"))
        assert len(matches) == 1
        for filename in ("README.md", "run.py", "test.py"):
            assert (matches[0] / filename).is_file()
    print("PASS：5 个专题的 Python 语法解析通过，示例页面和入口文件完整")


if __name__ == "__main__":
    # 被其他脚本导入时不自动执行自检。
    main()
