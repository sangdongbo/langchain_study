"""验证类型化输出及无效数量/单价的拒绝。"""

# ValidationError 是 Pydantic 字段约束失败；TestModel 提供可复现的结构化参数。
from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

# 复用本课实际的 Agent 和 schema，避免测试另写一套抽取规则。
from run import PROMPT, Purchase, build_agent

# 只允许官方离线模型，不读取 .env 或访问模型服务。
models.ALLOW_MODEL_REQUESTS = False
# 基准数据保持完整，后面的失败用例每次仅替换一个字段。
FIELDS = dict(
    department="研发平台部", item="AI 推理服务器", quantity=4,
    unit_price_yuan=68000, supplier="北辰智能硬件",
)


def main() -> None:
    # custom_output_args 模拟模型通过输出工具提交字段，结果仍由 Purchase 校验。
    result = build_agent(TestModel(custom_output_args=FIELDS)).run_sync(PROMPT)
    assert isinstance(result.output, Purchase)
    assert result.output.quantity * result.output.unit_price_yuan == 272000
    # 字典合并生成新的输入；直接验证 schema 能拒绝无效值，不额外调用模型。
    for invalid in ({"quantity": 0}, {"unit_price_yuan": -1}, {"supplier": ""}):
        try:
            Purchase.model_validate(FIELDS | invalid)
        except ValidationError:
            # 预期的校验失败属于通过；没有抛错才说明约束失效。
            pass
        else:
            raise AssertionError(f"无效字段未被拒绝：{invalid}")
    print("02 PASS：类型化输出、正数与必填名称校验")


# 本课测试无需 Key，可以直接在课堂展示结构化结果与字段边界。
if __name__ == "__main__":
    main()
