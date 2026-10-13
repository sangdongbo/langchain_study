"""02：把采购需求抽取成经过校验的 Pydantic 对象。"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from pydantic_examples.config import build_model

PROMPT = "研发平台部采购 4 台 AI 推理服务器，单价 68000 元，供应商北辰智能硬件。"


class Purchase(BaseModel):
    department: str = Field(min_length=1, description="申请部门")
    item: str = Field(min_length=1, description="采购物品")
    quantity: int = Field(gt=0, description="采购数量")
    unit_price_yuan: int = Field(gt=0, description="单价；本例只接受整数元")
    supplier: str = Field(min_length=1, description="供应商名称")


def build_agent(model: Model) -> Agent[None, Purchase]:
    return Agent(
        model,
        output_type=Purchase,
        instructions="从完整的采购需求抽取字段，保留用户原文中的名称，不添加猜测。",
        retries=2,
    )


def main() -> None:
    result = build_agent(build_model()).run_sync(
        PROMPT, usage_limits=UsageLimits(request_limit=4)
    )
    print(result.output.model_dump_json(indent=2))
    print("程序计算总额：", result.output.quantity * result.output.unit_price_yuan, "元")


if __name__ == "__main__":
    main()
