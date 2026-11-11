"""记录两种演示的动作、耗时和模型调用次数，不读取任何密钥。"""

# actions.json 是适配器小动作轨迹；metrics.json 是本轮汇总，不是浏览器全部事件日志。
# 认证不使用 action() 记录参数，以免把账号、验证码或登录凭据写入这些业务产物。

import json
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter


class RunLog:
    # 每轮入口各建一份实例，不跨任务累计；时间使用单调计时器，避免系统时钟校准影响。
    def __init__(self) -> None:
        self.started = perf_counter()
        self.elapsed: float | None = None
        self.actions: list[dict] = []

    @asynccontextmanager
    async def action(self, name: str, **parameters):
        # 拒绝的动作也记入轨迹，便于区分“模型尝试了”与“浏览器执行了”。
        started = perf_counter()
        # at_seconds 相对本轮起点；duration_seconds 记录单个动作耗时，两者含义不同。
        entry = {"action": name, "parameters": parameters,
                 "at_seconds": round(started - self.started, 3), "status": "success"}
        try:
            # yield 把控制权交回 async with 的动作实现，动作发生的异常会回到此处。
            yield
        except Exception as exc:
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            # 成功或普通异常都追加一条记录；失败后重新尝试属于另一条动作，而非覆盖旧记录。
            entry["duration_seconds"] = round(perf_counter() - started, 3)
            self.actions.append(entry)

    def stop(self) -> None:
        # 成功验收时停止计时，排除 --pause 等待用户的时间。
        if self.elapsed is None:
            # 只冻结一次，随后保存文件或等待用户不会把耗时越记越长。
            self.elapsed = round(perf_counter() - self.started, 3)

    def save(self, directory: Path, mode: str, status: str, keyword: str,
             limit: int, model_calls: int) -> None:
        # mode 区分 script/agent；keyword/limit 用来确认对比的是同一项业务任务。
        # 若异常分支尚未 stop，也在此冻结耗时；directory 由入口创建，按本次运行隔离。
        self.stop()
        metrics = {
            "mode": mode, "status": status, "keyword": keyword, "limit": limit,
            "elapsed_seconds": self.elapsed, "action_attempts": len(self.actions),
            # 包含 observe/read 等动作，不等于鼠标点击次数；done 不经过 OrderReader，不在此计数。
            "failed_actions": sum(item["status"] == "failed" for item in self.actions),
            # 统计 ainvoke 次数，包含失败调用；不等于 SDK 重试的 HTTP 请求数。
            "model_calls": model_calls,
        }
        for filename, data in (("actions.json", self.actions), ("metrics.json", metrics)):
            (directory / filename).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )


class CountedModel:
    """转发既有模型接口，只增加计数；离线替身与真实模型共用。"""

    def __init__(self, model) -> None:
        # 包裹既有模型而非重建配置，因此真实模型和离线替身都能使用相同的计数方式。
        self.inner = model
        self.calls = 0

    def __getattr__(self, name):
        # provider/model 等属性仍来自原模型，不复制或打印服务配置。
        return getattr(self.inner, name)

    async def ainvoke(self, messages, output_format=None, **kwargs):
        # 先加一再 await：即使模型抛错，本次尝试也计数；不展开模型 SDK 内部 HTTP 重试。
        # 不检查/打印 messages，也不自行读取密钥；真正请求仍由 inner 完成。
        self.calls += 1
        return await self.inner.ainvoke(messages, output_format, **kwargs)
