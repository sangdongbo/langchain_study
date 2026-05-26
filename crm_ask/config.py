from __future__ import annotations

from pathlib import Path


# v2 应用的基础配置集中放这里，避免 page/ui/agent 互相导入造成循环依赖。
APP_DIR = Path(__file__).resolve().parent

# Streamlit 运行缓存放在 v2 自己目录下，和原始 streamlit 示例隔离。
CACHE_PATH = APP_DIR / ".cache" / "conversations.json"

# 新建会话时的默认助手资料；侧边栏里可以继续修改并保存到本地缓存。
DEFAULT_TITLE = "小黑"
DEFAULT_PERSONA = "性格火辣的四川姑娘，回答直接、亲切，偶尔带一点俏皮。"
