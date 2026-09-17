from __future__ import annotations

import os
from pathlib import Path

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_opensandbox import OpenSandboxSandbox
from langsmith import tracing_context
from opensandbox.sync.sandbox import SandboxSync


PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env", override=False)

api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    raise RuntimeError("Set LLM_API_KEY or DEEPSEEK_API_KEY in ../.env")

model = ChatOpenAI(
    model=os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat",
    api_key=api_key,
    base_url=(
        os.getenv("LLM_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com/v1"
    ),
    temperature=0,
)

sandbox = SandboxSync.create(os.getenv("OPENSANDBOX_IMAGE") or "python:3.11-slim")
try:
    agent = create_deep_agent(
        model=model,
        backend=OpenSandboxSandbox(sandbox=sandbox),
        system_prompt="Work only inside the OpenSandbox container and report exit codes.",
    )
    with tracing_context(
        enabled=os.getenv("LANGSMITH_TRACING", "false").lower() == "true",
        project_name=os.getenv("LANGSMITH_PROJECT") or "deep-agent-examples",
        tags=["deep-agent-example", "opensandbox"],
    ):
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Create hello.py, run it, and return the exit code.",
                    }
                ]
            }
        )
        print(result["messages"][-1].content)
finally:
    sandbox.kill()
