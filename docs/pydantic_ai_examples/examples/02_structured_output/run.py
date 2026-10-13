"""02：把采购需求抽取成经过校验的 Pydantic 对象。"""

# BaseModel 定义输出对象；Field 把字段含义及约束加入模型输出的 schema。
from pydantic import BaseModel, Field
# Agent 执行抽取；Model 允许测试时替换模型；UsageLimits 防止无限请求。
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

# 各课共用模型配置，不在教学代码中填写密钥。
from pydantic_examples.config import build_model

# 样例给出所有必填信息，本课聚焦抽取与校验，不实现缺字段追问。
PROMPT = "研发平台部采购 4 台 AI 推理服务器，单价 68000 元，供应商北辰智能硬件。"


class Purchase(BaseModel):
    # 名称拒绝空字符串；这些约束不证明内容一定来自用户原文。
    department: str = Field(min_length=1, description="申请部门")
    item: str = Field(min_length=1, description="采购物品")
    # 数量和单价均为正整数；金额以整数元表示，避免这里引入浮点计算。
    quantity: int = Field(gt=0, description="采购数量")
    unit_price_yuan: int = Field(gt=0, description="单价；本例只接受整数元")
    supplier: str = Field(min_length=1, description="供应商名称")


def build_agent(model: Model) -> Agent[None, Purchase]:
    # 最终结果为 Purchase；默认工具输出模式要求模型通过输出工具提交结构化字段。
    return Agent(
        model,
        output_type=Purchase,
        instructions="从完整的采购需求抽取字段，保留用户原文中的名称，不添加猜测。",
        retries=2,  # 字段校验失败时允许模型修正，超过次数仍会报错。
    )


def main() -> None:
    # 真正的模型调用发生在 run_sync；请求总数还受 request_limit 约束。
    result = build_agent(build_model()).run_sync(
        PROMPT, usage_limits=UsageLimits(request_limit=4)
    )
    # result.output 已是校验后的对象；展示时转成 JSON，计算时直接读取字段。
    print(result.output.model_dump_json(indent=2))
    print("程序计算总额：", result.output.quantity * result.output.unit_price_yuan, "元")


# 只在终端直接执行本文件时运行真实模型演示。
if __name__ == "__main__":
    main()
