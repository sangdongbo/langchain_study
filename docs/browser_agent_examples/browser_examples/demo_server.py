"""为示例启动仅监听本机的静态网站。"""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import TracebackType

# 只提供项目内的静态演示页面，不依赖外部商城或数据库。
SITE_DIR = Path(__file__).resolve().parents[1] / "demo_site"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        # 省略每个静态资源的访问日志，让终端聚焦示例结果。
        pass

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            # 浏览器关闭时可能主动中断仍在传输的静态资源。
            pass


class DemoServer:
    def __init__(self) -> None:
        # 固定资源目录，不需要通过 chdir 改动整个进程的工作目录。
        handler = partial(QuietHandler, directory=str(SITE_DIR))
        # 127.0.0.1 仅供本机访问；端口 0 让系统分配空闲端口，便于并行演示。
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        # HTTP 服务在后台线程运行，主线程继续执行浏览器操作。
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        # 返回实际分配的端口；不要在示例里硬编码 8000 或 8765。
        return f"http://127.0.0.1:{self._server.server_port}"

    def __enter__(self) -> "DemoServer":
        # with DemoServer() as site 进入时开始处理请求。
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # 无论示例正常结束还是抛出异常，都停止服务、释放端口并等待线程退出。
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
