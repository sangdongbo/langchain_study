from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any


COLLECTION_DEFAULT = "learnone_rag_chunking_demo_01"
CONTAINER_DEFAULT = "milvus-standalone"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="只读诊断 Milvus Collection 长时间处于 Loading 的原因。"
    )
    parser.add_argument("--uri", default="http://127.0.0.1:19530")
    parser.add_argument("--database", default="default")
    parser.add_argument("--collection", default=COLLECTION_DEFAULT)
    parser.add_argument("--token", default="")
    parser.add_argument("--docker-container", default=CONTAINER_DEFAULT)
    parser.add_argument("--log-tail", type=int, default=2000)
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="只检查 Milvus API，不读取 Docker 状态和日志。",
    )
    return parser.parse_args()


def heading(title: str) -> None:
    print(f"\n{'=' * 12} {title} {'=' * 12}")


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def safe_call(label: str, operation: Callable[[], Any]) -> Any | None:
    try:
        value = operation()
        print(f"{label}: {json_text(value)}")
        return value
    except Exception as exc:  # 诊断脚本需要继续收集其他信息。
        print(f"{label}: ERROR {type(exc).__name__}: {exc}")
        return None


def run_docker(*arguments: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def inspect_docker(container: str, log_tail: int) -> list[str]:
    heading("Docker")
    inspect_result = run_docker(
        "inspect",
        container,
        "--format",
        (
            "Image={{.Config.Image}} Status={{.State.Status}} "
            "Health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} "
            "OOMKilled={{.State.OOMKilled}} RestartCount={{.RestartCount}}"
        ),
    )
    if inspect_result.returncode != 0:
        print(f"docker inspect: ERROR {inspect_result.stderr.strip()}")
        return []
    print(inspect_result.stdout.strip())

    stats_result = run_docker(
        "stats",
        "--no-stream",
        "--format",
        "CPU={{.CPUPerc}} Memory={{.MemUsage}} MemoryPercent={{.MemPerc}}",
        container,
    )
    if stats_result.returncode == 0:
        print(stats_result.stdout.strip())
    else:
        print(f"docker stats: ERROR {stats_result.stderr.strip()}")

    logs_result = run_docker("logs", "--tail", str(log_tail), container, timeout=30)
    logs = f"{logs_result.stdout}\n{logs_result.stderr}".splitlines()
    print(f"读取 Docker 日志行数: {len(logs)}")
    return logs


def inspect_milvus(args: argparse.Namespace) -> dict[str, Any]:
    heading("Milvus API")
    try:
        import pymilvus
        from pymilvus import MilvusClient
    except ImportError as exc:
        print(f"无法导入 pymilvus: {exc}")
        print("请使用项目虚拟环境运行，例如 .venv\\Scripts\\python.exe。")
        return {}

    print(f"PyMilvus version: {pymilvus.__version__}")
    try:
        client = MilvusClient(
            uri=args.uri,
            token=args.token,
            db_name=args.database,
            timeout=10,
        )
    except Exception as exc:
        print(f"连接 Milvus 失败: {type(exc).__name__}: {exc}")
        return {}

    result: dict[str, Any] = {}
    result["server_type"] = safe_call("Server type", client.get_server_type)
    result["server_version"] = safe_call(
        "Server version", lambda: client.get_server_version(timeout=10)
    )
    has_collection = safe_call(
        "Collection exists",
        lambda: client.has_collection(
            collection_name=args.collection,
            timeout=10,
        ),
    )
    result["has_collection"] = has_collection
    if has_collection is not True:
        return result

    result["description"] = safe_call(
        "Collection description",
        lambda: client.describe_collection(args.collection, timeout=10),
    )
    result["stats"] = safe_call(
        "Collection stats",
        lambda: client.get_collection_stats(args.collection, timeout=10),
    )
    result["load_state"] = safe_call(
        "Load state",
        lambda: client.get_load_state(args.collection, timeout=10),
    )

    index_names = safe_call(
        "Index names",
        lambda: client.list_indexes(args.collection),
    )
    if isinstance(index_names, list):
        result["indexes"] = []
        for index_name in index_names:
            description = safe_call(
                f"Index {index_name}",
                lambda name=index_name: client.describe_index(
                    args.collection,
                    name,
                    timeout=10,
                ),
            )
            result["indexes"].append(description)

    result["loaded_segments"] = safe_call(
        "Loaded segments",
        lambda: client.list_loaded_segments(args.collection, timeout=10),
    )
    return result


def analyze(logs: list[str], milvus_info: dict[str, Any]) -> int:
    heading("诊断结论")
    normalized_logs = "\n".join(logs).lower()
    findings: list[tuple[str, str]] = []

    if "bloom_filter" in normalized_logs and "key not found" in normalized_logs:
        findings.append(
            (
                "CRITICAL",
                "Milvus 元数据引用了不存在的 Bloom Filter 统计文件，"
                "QueryNode 无法加载 segment。这会让 Collection 永久停留在 Loading。",
            )
        )
    if "failed to load growing segment" in normalized_logs:
        findings.append(
            ("ERROR", "Growing segment 加载失败，服务正在反复重试加载任务。")
        )
    if "oomkilled=true" in normalized_logs or "out of memory" in normalized_logs:
        findings.append(("ERROR", "日志显示内存不足或容器被 OOM Killer 终止。"))
    if "no available query node" in normalized_logs:
        findings.append(("ERROR", "没有可用 QueryNode。"))

    load_state = milvus_info.get("load_state")
    if isinstance(load_state, dict):
        state = str(load_state.get("state") or load_state.get("load_state") or "")
        if state:
            findings.append(("INFO", f"Milvus API 返回的加载状态为 {state}。"))

    if not findings:
        print("没有从当前日志和 API 信息中识别到已知故障模式。")
        print("请增加 --log-tail 后重试，并检查 Attu 与 Milvus 的版本兼容性。")
        return 0

    for level, message in findings:
        print(f"[{level}] {message}")

    if any(level == "CRITICAL" for level, _ in findings):
        print(
            "\n建议：先备份/保留当前 Docker volume，停止继续点击 Load。"
            "当前数据只有少量测试记录时，最稳妥的处理通常是换用稳定版 Milvus，"
            "并由原始文档重新创建 Collection；不要直接手工删除内部 files 路径。"
        )
        return 2
    if any(level == "ERROR" for level, _ in findings):
        return 1
    return 0


def main() -> int:
    args = parse_args()
    logs = [] if args.skip_docker else inspect_docker(
        args.docker_container,
        args.log_tail,
    )
    milvus_info = inspect_milvus(args)
    return analyze(logs, milvus_info)


if __name__ == "__main__":
    sys.exit(main())
