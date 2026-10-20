from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from insightpilot.verification import (
    ClaimStatus,
    ClaimVerification,
    CriticDecision,
    CriticIssue,
    CriticReport,
    EvidenceExecutionStatus,
    EvidenceLedger,
    IssueSeverity,
    VerificationReport,
    VerificationStatus,
)


def test_ledger_generates_ids_and_preserves_insertion_order() -> None:
    ledger = EvidenceLedger()

    first = ledger.add("profile_dataset", {}, {"rows": 8}, mode="preflight")
    second = ledger.add(
        "group_metric",
        {"dimension_col": "product"},
        {"records": [{"product": "Laptop", "value": 34800}]},
        mode="direct",
    )

    assert first.evidence_id == "E0001"
    assert second.evidence_id == "E0002"
    assert [item.evidence_id for item in ledger.all()] == ["E0001", "E0002"]
    assert len(ledger) == 2


def test_ledger_detects_error_results_automatically() -> None:
    ledger = EvidenceLedger()
    item = ledger.add(
        "period_metric",
        {},
        {"status": "error", "message": "date column missing"},
        mode="planned",
        plan_step_id="step_02",
    )

    assert item.execution_status is EvidenceExecutionStatus.ERROR
    assert item.plan_step_id == "step_02"


def test_ledger_accepts_explicit_execution_status() -> None:
    ledger = EvidenceLedger()
    item = ledger.add(
        "some_tool", {}, {"value": 1}, mode="direct", execution_status="error"
    )
    assert item.execution_status is EvidenceExecutionStatus.ERROR


def test_ledger_copies_input_and_returned_items() -> None:
    ledger = EvidenceLedger()
    arguments = {"filters": {"region": "north"}}
    result = {"records": [{"value": 3}]}
    item = ledger.add("group_metric", arguments, result, mode="direct")

    arguments["filters"]["region"] = "south"
    result["records"][0]["value"] = 99
    item.result["records"][0]["value"] = 100

    saved = ledger.get("E0001")
    assert saved is not None
    assert saved.arguments["filters"]["region"] == "north"
    assert saved.result["records"][0]["value"] == 3


def test_ledger_returns_none_for_unknown_id() -> None:
    assert EvidenceLedger().get("E9999") is None


def test_ledger_converts_numpy_and_pandas_values_to_json_safe_values() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "sample_tool",
        {"limit": np.int64(4)},
        {
            "value": np.float64(2.5),
            "missing": np.float64(np.nan),
            "at": pd.Timestamp("2026-10-20T08:00:00Z"),
        },
        mode="planned",
    )

    serialized = json.loads(ledger.to_prompt_context())
    item = serialized["items"][0]
    assert item["arguments"]["limit"] == 4
    assert item["result"]["value"] == 2.5
    assert item["result"]["missing"] is None
    assert item["result"]["at"] == "2026-10-20T08:00:00+00:00"


def test_ledger_clear_resets_items_and_ids() -> None:
    ledger = EvidenceLedger()
    ledger.add("a", {}, {}, mode="direct")
    ledger.clear()

    assert len(ledger) == 0
    assert ledger.to_dict() == {"items": [], "count": 0}
    assert ledger.add("b", {}, {}, mode="direct").evidence_id == "E0001"


def test_ledger_validates_required_inputs() -> None:
    ledger = EvidenceLedger()
    with pytest.raises(ValueError, match="tool_name"):
        ledger.add("", {}, {}, mode="direct")
    with pytest.raises(TypeError, match="arguments"):
        ledger.add("tool", [], {}, mode="direct")  # type: ignore[arg-type]  # Kiểm thử cố tình truyền đối số sai kiểu dữ liệu.
    with pytest.raises(TypeError, match="result"):
        ledger.add("tool", {}, [], mode="direct")  # type: ignore[arg-type]  # Kiểm thử cố tình truyền đối số sai kiểu dữ liệu.


def test_verification_report_serializes_enum_values() -> None:
    report = VerificationReport(
        overall_status=VerificationStatus.PARTIALLY_VERIFIED,
        summary="One claim needs a qualification.",
        claims=[
            ClaimVerification(
                claim_id="C001",
                claim="Revenue fell by 35.58%.",
                status=ClaimStatus.VERIFIED,
                evidence_ids=["E0001"],
                explanation="Matches the comparison Tool result.",
                severity=IssueSeverity.LOW,
            )
        ],
    )

    value = report.to_dict()
    assert value["overall_status"] == "PARTIALLY_VERIFIED"
    assert value["claims"][0]["status"] == "VERIFIED"
    assert value["claims"][0]["evidence_ids"] == ["E0001"]


def test_critic_report_serializes_issues_and_revision_instructions() -> None:
    report = CriticReport(
        decision=CriticDecision.NEEDS_REVISION,
        summary="The causal explanation is unsupported.",
        issues=[
            CriticIssue(
                issue_type="unsupported_claim",
                description="No evidence links ad performance to revenue change.",
                related_claim_id="C002",
                severity=IssueSeverity.HIGH,
            )
        ],
        revision_instructions=["Remove the unsupported causal explanation."],
    )

    value = report.to_dict()
    assert value["decision"] == "NEEDS_REVISION"
    assert value["issues"][0]["severity"] == "high"
    assert value["revision_instructions"] == [
        "Remove the unsupported causal explanation."
    ]
