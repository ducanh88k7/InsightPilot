from __future__ import annotations

import json

import pytest
from dataclasses import dataclass
from pathlib import Path

from insightpilot.agent import DataAnalystAgent
from insightpilot.tools import AnalysisContext, ToolRegistry, build_data_tools

ROOT = Path(__file__).parent.parent
DATASET = ROOT / "data" / "sample_sales.csv"


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_data_tools():
        registry.register(tool)
    return registry


def build_context() -> AnalysisContext:
    context = AnalysisContext()
    build_registry().execute("load_dataset", {"path": str(DATASET)}, context)
    return context


@dataclass
class FakeFunctionCall:
    type: str
    name: str
    arguments: str
    call_id: str


@dataclass
class FakeMessage:
    type: str
    text: str = ""


@dataclass
class FakeResponse:
    output: list
    output_text: str


class FakeResponses:
    def __init__(self, mode: str = "basic") -> None:
        self.calls = []
        self.step = 0
        self.mode = mode
        self.review_count = 0

    def create(self, *, model, input, tools=None, text=None):
        self.calls.append({"model": model, "input": input, "tools": tools, "text": text})

        # Các lần gọi đầu ra có cấu trúc được phân biệt theo tên schema.
        format_name = ((text or {}).get("format") or {}).get("name")
        if format_name == "critic_review":
            if self.mode == "review_failure":
                raise RuntimeError("simulated critic API failure")
            self.review_count += 1
            context = json.loads(input[1]["content"])
            evidence_items = context["evidence_ledger"]["items"]
            successful = [
                item for item in evidence_items
                if item["execution_status"] == "success" and item["result"].get("status") != "error"
            ]
            evidence_ids = [successful[-1]["evidence_id"]] if successful else []
            draft = context["draft_answer"]
            # Lượt review đầu mô phỏng trường hợp Critic bỏ sót nội dung trong bản tóm tắt dự phòng.
            # Ở lượt review sau, giả lập Critic đã trích đúng nội dung từ câu trả lời mới.
            claim_text = (
                "The planned execution summary is available."
                if self.mode == "synthesis_failure" and self.review_count == 1
                else draft
            )
            claim_status = "VERIFIED"
            decision = "PASS"
            explanation = "Supported by successful Tool evidence recorded for this turn."
            severity = "low"
            instructions = []
            issues = []
            if self.mode in {"needs_revision", "revision_still_bad"} and self.review_count == 1:
                claim_status = "UNSUPPORTED"
                decision = "NEEDS_REVISION"
                explanation = "The causal statement is not supported by the supplied evidence."
                severity = "high"
                instructions = ["Remove unsupported causal claims and state the observable change only."]
                issues = [{
                    "issue_type": "unsupported_claim",
                    "description": "A cause was stated without supporting evidence.",
                    "related_claim_id": "C001",
                    "severity": "high",
                }]
            elif self.mode == "unknown_evidence":
                evidence_ids = ["E9999"]
            elif self.mode == "revision_still_bad":
                claim_status = "UNSUPPORTED"
                decision = "NEEDS_REVISION"
                explanation = "The revised statement remains unsupported."
                severity = "high"
                instructions = ["Remove unsupported claims."]
            payload = {
                "verification": {
                    "summary": "Fake verification summary.",
                    "claims": [{
                        "claim_id": "C001",
                        "claim": claim_text,
                        "status": claim_status,
                        "evidence_ids": evidence_ids,
                        "explanation": explanation,
                        "severity": severity,
                    }],
                },
                "critic": {
                    "decision": decision,
                    "summary": "Fake critic summary.",
                    "issues": issues,
                    "revision_instructions": instructions,
                },
            }
            return FakeResponse(output=[], output_text=json.dumps(payload))

        if format_name == "analysis_plan":
            if self.mode == "planner_failure":
                raise RuntimeError("simulated planner API failure")

            planned_metric = "profit" if self.mode == "planned_tool_failure" else "revenue"
            payload = {
                "goal": "Find the top product by revenue and compare the latest two months",
                "steps": [
                    {
                        "id": "step_1",
                        "purpose": "Find the top product by total revenue.",
                        "tool_name": "group_metric",
                        "arguments_json": json.dumps(
                            {
                                "dimension_col": "product",
                                "metric_col": planned_metric,
                                "agg": "sum",
                                "top_n": 1,
                            }
                        ),
                        "depends_on": [],
                    },
                    {
                        "id": "step_2",
                        "purpose": "Compare the two most recent monthly revenue totals.",
                        "tool_name": "compare_last_two_periods",
                        "arguments_json": json.dumps(
                            {
                                "date_col": "date",
                                "metric_col": "revenue",
                                "freq": "MS",
                                "agg": "sum",
                            }
                        ),
                        "depends_on": ["step_1"] if self.mode == "planned_tool_failure" else [],
                    },
                ],
            }
            return FakeResponse(output=[], output_text=json.dumps(payload))

        # Yêu cầu sửa câu trả lời không được cấp Tool và sử dụng danh sách messages.
        if (
            tools == []
            and isinstance(input, list)
            and input
            and "revising an AI data analyst's answer" in input[0].get("content", "")
        ):
            if self.mode == "revision_failure":
                raise RuntimeError("simulated answer revision failure")
            if self.mode == "numeric_mismatch":
                return FakeResponse(
                    output=[FakeMessage(type="message", text="Revenue decreased by 35.58%.")],
                    output_text="Revenue decreased by 35.58%.",
                )
            return FakeResponse(
                output=[FakeMessage(type="message", text="The observed change is supported; its cause is not established by the available data.")],
                output_text="The observed change is supported; its cause is not established by the available data.",
            )

        # Lần tổng hợp ở Planned Mode: tools=[] cho biết đây là giai đoạn không dùng Tool.
        if tools == [] and self.mode in {"planned", "planned_tool_failure", "synthesis_failure", "numeric_mismatch"}:
            if self.mode == "synthesis_failure":
                raise RuntimeError("simulated synthesis API failure")
            planned_answer = (
                "Revenue decreased by 30%."
                if self.mode == "numeric_mismatch"
                else "Planned analysis completed successfully."
            )
            return FakeResponse(
                output=[FakeMessage(type="message", text=planned_answer)],
                output_text=planned_answer,
            )

        self.step += 1

        if self.mode in {"basic", "recovery", "planner_failure", "needs_revision", "revision_still_bad", "review_failure", "unknown_evidence"}:
            if self.mode in {"basic", "planner_failure", "needs_revision", "revision_still_bad", "review_failure", "unknown_evidence"}:
                if self.step == 1:
                    return FakeResponse(
                        output=[
                            FakeFunctionCall(
                                type="function_call",
                                name="group_metric",
                                arguments=json.dumps(
                                    {
                                        "dimension_col": "product",
                                        "metric_col": "revenue",
                                        "agg": "sum",
                                        "top_n": 3,
                                    }
                                ),
                                call_id="call_1",
                            )
                        ],
                        output_text="",
                    )

                return FakeResponse(
                    output=[FakeMessage(type="message", text="Laptop is the top product by total revenue.")],
                    output_text="Laptop is the top product by total revenue.",
                )

            if self.step == 1:
                return FakeResponse(
                    output=[
                        FakeFunctionCall(
                            type="function_call",
                            name="group_metric",
                            arguments=json.dumps(
                                {
                                    "dimension_col": "product",
                                    "metric_col": "profit",
                                    "agg": "sum",
                                    "top_n": 3,
                                }
                            ),
                            call_id="call_bad",
                        )
                    ],
                    output_text="",
                )
            if self.step == 2:
                return FakeResponse(
                    output=[
                        FakeFunctionCall(
                            type="function_call",
                            name="group_metric",
                            arguments=json.dumps(
                                {
                                    "dimension_col": "product",
                                    "metric_col": "revenue",
                                    "agg": "sum",
                                    "top_n": 3,
                                }
                            ),
                            call_id="call_good",
                        )
                    ],
                    output_text="",
                )
            return FakeResponse(
                output=[FakeMessage(type="message", text="Doanh thu đã được phân tích thành công.")],
                output_text="Doanh thu đã được phân tích thành công.",
            )

        raise ValueError(f"Unknown fake mode: {self.mode}")


class FakeClient:
    def __init__(self, mode: str = "basic") -> None:
        self.responses = FakeResponses(mode=mode)


def build_test_agent(
    mode: str = "basic",
    planning_mode: str = "auto",
    fallback_to_direct: bool = True,
) -> DataAnalystAgent:
    registry = build_registry()
    context = AnalysisContext()
    registry.execute("load_dataset", {"path": str(DATASET)}, context)

    return DataAnalystAgent(
        client=FakeClient(mode=mode),
        registry=registry,
        context=context,
        model="test-model",
        max_iterations=4,
        planning_mode=planning_mode,
        fallback_to_direct=fallback_to_direct,
    )


def test_agent_executes_tool_and_returns_final_answer():
    agent = build_test_agent()

    result = agent.ask("What is the top product by total revenue?")

    assert result.answer == "Laptop is the top product by total revenue."
    assert result.iterations == 2
    assert result.mode == "direct"
    assert result.llm_requests == 3  # Vòng lặp Direct Mode cộng với lượt review của Critic
    assert result.tool_call_count == len(result.tool_calls)
    assert result.duration_ms >= 0
    assert result.tool_calls[0]["name"] == "profile_dataset"
    assert result.tool_calls[0]["phase"] == "preflight"
    assert any(call["name"] == "add_revenue_column" for call in result.tool_calls)
    assert any(call["name"] == "group_metric" for call in result.tool_calls)


def test_agent_exposes_all_tools_to_model():
    agent = build_test_agent()
    tools = agent._openai_tools()

    assert {tool["name"] for tool in tools} == {
        "add_revenue_column",
        "compare_last_two_periods",
        "group_metric",
        "load_dataset",
        "period_metric",
        "profile_dataset",
    }
    assert all(tool["type"] == "function" for tool in tools)
    assert all(tool["strict"] is False for tool in tools)


def test_preflight_creates_revenue_for_revenue_questions():
    agent = build_test_agent()

    result = agent.ask("What are the top 3 products by revenue?")

    assert agent.context.df is not None
    assert "revenue" in agent.context.df.columns
    assert result.tool_calls[0]["name"] == "profile_dataset"
    assert result.tool_calls[1]["name"] == "add_revenue_column"
    assert result.tool_calls[1]["phase"] == "preflight"


def test_agent_recovers_from_tool_error():
    agent = build_test_agent(mode="recovery")

    result = agent.ask("Hãy tìm top 3 sản phẩm theo doanh thu.")

    assert result.answer == "Doanh thu đã được phân tích thành công."
    assert result.iterations == 3
    assert result.mode == "direct"
    assert result.tool_calls[-2]["arguments"]["metric_col"] == "profit"
    assert result.tool_calls[-1]["arguments"]["metric_col"] == "revenue"


def test_vietnamese_language_is_requested_in_prompt():
    agent = build_test_agent()
    response = agent.client.responses

    agent.ask("Hãy tìm sản phẩm có doanh thu cao nhất.")

    first_input = response.calls[0]["input"][0]["content"]
    assert "same language" in first_input.lower()
    assert "Vietnamese" in first_input


def test_complex_question_uses_planner_and_executor():
    agent = build_test_agent(mode="planned", planning_mode="auto")

    result = agent.ask(
        "Why did revenue change between the latest two months, and which product was the top contributor?"
    )

    assert result.mode == "planned"
    assert result.iterations == 1  # Một lượt điều phối theo kế hoạch, không phải số lần gọi API
    assert result.llm_requests == 3  # Planner + tổng hợp + yêu cầu review của Critic
    assert result.tool_call_count == len(result.tool_calls)
    assert result.plan_steps_total == 2
    assert result.plan_steps_completed == 2
    assert result.plan_steps_failed == 0
    assert result.plan_steps_blocked == 0
    assert result.duration_ms >= 0
    assert result.plan is not None
    assert result.plan["status"] == "completed"
    assert any(call["phase"] == "plan_executor" for call in result.tool_calls)
    assert result.answer == "Planned analysis completed successfully."


def test_planning_mode_never_forces_direct_path():
    agent = build_test_agent(mode="basic", planning_mode="never")
    result = agent.ask("Why did revenue change between the latest two months?")

    assert result.mode == "direct"
    assert result.answer == "Laptop is the top product by total revenue."


def test_planning_mode_always_uses_planner():
    agent = build_test_agent(mode="planned", planning_mode="always")
    result = agent.ask("What is the top product?")

    assert result.mode == "planned"
    assert result.plan is not None



def test_planner_failure_falls_back_to_direct_and_is_observable():
    agent = build_test_agent(mode="planner_failure", planning_mode="always")

    result = agent.ask("What is the top product by revenue?")

    assert result.mode == "direct"
    assert result.fallback_used is True
    assert "Planner could not produce a valid plan" in result.fallback_reason
    assert result.llm_requests == 4  # Planner thất bại + hai lần gọi vòng lặp Direct Mode + yêu cầu review của Critic
    assert any("switched to Direct Mode" in warning for warning in result.warnings)
    assert result.answer == "Laptop is the top product by total revenue."


def test_planner_failure_is_raised_when_fallback_is_disabled():
    from insightpilot.agent.core import PlannerBuildError

    agent = build_test_agent(
        mode="planner_failure",
        planning_mode="always",
        fallback_to_direct=False,
    )

    with pytest.raises(PlannerBuildError, match="Planner could not produce a valid plan"):
        agent.ask("What is the top product by revenue?")


def test_synthesis_fallback_with_uncovered_claim_is_revised_without_reexecuting_tools():
    agent = build_test_agent(mode="synthesis_failure", planning_mode="always")

    result = agent.ask("What is the top product by revenue?")

    assert result.mode == "planned"
    assert result.fallback_used is False
    # Planner + tổng hợp lỗi + review + sửa câu trả lời + review lại.
    assert result.llm_requests == 5
    assert result.review_attempts == 2
    assert result.plan_steps_completed == 2
    assert result.verification_report["claim_coverage_report"]["status"] == "COMPLETE"
    assert "The observed change is supported" in result.answer
    assert any("Final synthesis request failed" in warning for warning in result.warnings)


def test_planned_tool_failure_is_reported_without_direct_reexecution():
    agent = build_test_agent(mode="planned_tool_failure", planning_mode="always")

    result = agent.ask("What is the top product by revenue?")

    assert result.mode == "planned"
    assert result.fallback_used is False
    assert result.plan_steps_failed == 1
    assert result.plan_steps_blocked == 1
    assert result.plan["status"] == "failed"
    assert result.llm_requests == 3  # Planner + tổng hợp + các yêu cầu review của Critic
    assert any(
        call.get("status") == "failed" and call.get("phase") == "plan_executor"
        for call in result.tool_calls
    )


def test_evidence_ledger_records_preflight_and_direct_tool_results():
    agent = build_test_agent()

    result = agent.ask("What is the top product by total revenue?")

    items = result.evidence_ledger["items"]
    assert len(items) == 4
    assert [item["evidence_id"] for item in items] == ["E0001", "E0002", "E0003", "E0004"]
    assert {item["mode"] for item in items} == {"preflight", "direct"}
    assert items[-1]["tool_name"] == "group_metric"
    assert result.verification_report["overall_status"] == "VERIFIED"
    assert result.critic_report["decision"] == "PASS"


def test_evidence_ledger_records_planned_step_ids():
    agent = build_test_agent(mode="planned", planning_mode="always")

    result = agent.ask("What is the top product by revenue?")

    planned_items = [
        item for item in result.evidence_ledger["items"]
        if item["mode"] == "planned"
    ]
    assert len(planned_items) == 2
    assert {item["plan_step_id"] for item in planned_items} == {"step_1", "step_2"}
    assert result.verification_report["overall_status"] == "VERIFIED"


def test_critic_revision_happens_once_without_reexecuting_tools():
    agent = build_test_agent(mode="needs_revision", planning_mode="never")

    result = agent.ask("Why did revenue change?")

    assert result.review_attempts == 2
    assert result.critic_report["decision"] == "PASS"
    assert "cause is not established" in result.answer
    # Lập hồ sơ + tính doanh thu + cập nhật hồ sơ + một Tool dữ liệu; bước sửa không dùng Tool.
    assert len(result.evidence_ledger["items"]) == len(result.tool_calls)
    assert result.llm_requests == 5


def test_numeric_mismatch_triggers_one_revision_without_reexecuting_tools():
    agent = build_test_agent(mode="numeric_mismatch", planning_mode="always")

    result = agent.ask("Compare the last two months of revenue.")

    assert result.answer == "Revenue decreased by 35.58%."
    assert result.review_attempts == 2
    assert result.critic_report["decision"] == "PASS"
    assert result.verification_report["numeric_report"]["status"] == "PASSED"
    # Planner + tổng hợp + review + sửa + review cuối; không chạy lại Tool nào.
    assert result.llm_requests == 5
    assert len(result.evidence_ledger["items"]) == len(result.tool_calls)


def test_reviewer_failure_is_visible_and_never_marked_pass():
    agent = build_test_agent(mode="review_failure")

    result = agent.ask("What is the top product by revenue?")

    assert result.critic_report["decision"] == "REVIEW_ERROR"
    assert result.verification_report["overall_status"] == "INSUFFICIENT_EVIDENCE"
    assert "not been confirmed" in result.answer
    assert any("Critic review failed" in warning for warning in result.warnings)


def test_unknown_evidence_ids_cannot_make_a_claim_verified():
    agent = build_test_agent(mode="unknown_evidence")

    result = agent.ask("What is the top product by revenue?")

    assert all(
        claim["status"] != "VERIFIED"
        for claim in result.verification_report["claims"]
    )
    assert result.critic_report["decision"] != "PASS"
    assert "after one revision" in result.answer


def test_unresolved_claim_after_one_revision_is_reported_without_looping():
    agent = build_test_agent(mode="revision_still_bad", planning_mode="never")

    result = agent.ask("Why did revenue change?")

    assert result.review_attempts == 2
    assert result.critic_report["decision"] == "NEEDS_REVISION"
    assert "after one revision" in result.answer
    assert len(result.evidence_ledger["items"]) == len(result.tool_calls)


def test_no_successful_tool_evidence_is_reported_as_insufficient():
    registry = build_registry()
    agent = DataAnalystAgent(
        client=FakeClient(mode="basic"),
        registry=registry,
        context=AnalysisContext(),
        model="test-model",
        max_iterations=4,
        planning_mode="never",
    )

    result = agent.ask("What is the top product by total revenue?")

    assert result.critic_report["decision"] == "INSUFFICIENT_EVIDENCE"
    assert result.verification_report["overall_status"] == "INSUFFICIENT_EVIDENCE"
    assert all(
        item["execution_status"] == "error"
        for item in result.evidence_ledger["items"]
    )
    assert "not enough successful Tool evidence" in result.answer
