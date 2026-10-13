"""不启动浏览器、不调用模型的项目静态自检。"""

import ast
from html.parser import HTMLParser
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


class TestIdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.test_ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "data-testid" and value:
                self.test_ids.add(value)


def main() -> None:
    for directory in (PROJECT_DIR / "browser_examples", PROJECT_DIR / "examples"):
        for path in directory.rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parser = TestIdParser()
    parser.feed((PROJECT_DIR / "demo_site" / "index.html").read_text(encoding="utf-8"))
    assert {"keyword", "category", "max-price", "apply-filter", "result-status"} <= parser.test_ids
    assert (PROJECT_DIR / "demo_site" / "login.html").is_file()
    assert (PROJECT_DIR / "demo_site" / "dashboard.html").is_file()
    assert (PROJECT_DIR / "demo_site" / "detail.html").is_file()
    for number in range(1, 6):
        matches = list((PROJECT_DIR / "examples").glob(f"{number:02d}_*"))
        assert len(matches) == 1
        for filename in ("README.md", "run.py", "test.py"):
            assert (matches[0] / filename).is_file()
    print("PASS：5 个专题的 Python 语法解析通过，示例页面和入口文件完整")


if __name__ == "__main__":
    main()
