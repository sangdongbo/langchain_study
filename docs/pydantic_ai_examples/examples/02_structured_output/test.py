"""验证类型化输出及无效数量/单价的拒绝。"""

from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from run import PROMPT, Purchase, build_agent

models.ALLOW_MODEL_REQUESTS = False
FIELDS = dict(
    department="研发平台部", item="AI 推理服务器", quantity=4,
    unit_price_yuan=68000, supplier="北辰智能硬件",
)


def main() -> None:
    result = build_agent(TestModel(custom_output_args=FIELDS)).run_sync(PROMPT)
    assert isinstance(result.output, Purchase)
    assert result.output.quantity * result.output.unit_price_yuan == 272000
    for invalid in ({"quantity": 0}, {"unit_price_yuan": -1}, {"supplier": ""}):
        try:
            Purchase.model_validate(FIELDS | invalid)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"无效字段未被拒绝：{invalid}")
    print("02 PASS：类型化输出、正数与必填名称校验")


if __name__ == "__main__":
    main()
