from __future__ import annotations

import json
from dataclasses import dataclass

from insightpilot.verification import (
    ClaimStatus,
    ClaimVerification,
    CriticDecision,
    CriticVerifier,
    EvidenceLedger,
    NumericCheckStatus,
    NumericVerificationStatus,
    NumericVerifier,
    VerificationReport,
    VerificationStatus,
)


def _comparison_ledger(*, stored_percentage: float = -35.58) -> EvidenceLedger:
    ledger = EvidenceLedger()
    ledger.add(
        "compare_last_two_periods",
        {"date_col": "date", "metric_col": "revenue"},
        {
            "status": "ok",
            "previous": 26000.0,
            "current": 16750.0,
            "absolute_change": -9250.0,
            # Bộ kiểm tra phải tự tính từ previous/current thay vì tin giá trị có sẵn.
            "percentage_change": stored_percentage,
        },
        mode="direct",
    )
    return ledger


def _verification(claim: str, evidence_id: str = "E0001") -> VerificationReport:
    return VerificationReport(
        overall_status=VerificationStatus.VERIFIED,
        claims=[
            ClaimVerification(
                claim_id="C001",
                claim=claim,
                status=ClaimStatus.VERIFIED,
                evidence_ids=[evidence_id],
            )
        ],
    )


def test_correct_percentage_is_verified_from_previous_and_current_values() -> None:
    ledger = _comparison_ledger(stored_percentage=-999.0)
    report = NumericVerifier().verify(
        _verification("Revenue decreased by 35.58%."), ledger
    )

    assert report.status is NumericVerificationStatus.PASSED
    assert report.findings[0].status is NumericCheckStatus.VERIFIED
    assert abs(report.findings[0].expected_values[0] - (-35.5769230769)) < 1e-6


def test_wrong_percentage_is_detected_even_if_llm_called_it_verified() -> None:
    ledger = _comparison_ledger()
    report = NumericVerifier().verify(
        _verification("Revenue decreased by 30%."), ledger
    )

    assert report.status is NumericVerificationStatus.ISSUES_FOUND
    assert report.findings[0].status is NumericCheckStatus.MISMATCH
    assert report.findings[0].expected_values == [-35.57692307692308]


def test_wrong_direction_is_detected_when_magnitude_is_correct() -> None:
    ledger = _comparison_ledger()
    report = NumericVerifier().verify(
        _verification("Revenue increased by 35.58%."), ledger
    )

    assert report.findings[0].status is NumericCheckStatus.MISMATCH


def test_different_directions_in_one_sentence_are_checked_per_clause() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "revenue"},
        {"previous": 26000.0, "current": 16750.0, "status": "ok"},
        mode="direct",
    )
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "profit"},
        {"previous": 100.0, "current": 120.0, "status": "ok"},
        mode="direct",
    )
    verification = _verification(
        "Revenue decreased by 35.58%, while profit increased by 20%.",
        evidence_id="E0001",
    )
    verification.claims[0].evidence_ids.append("E0002")

    report = NumericVerifier().verify(verification, ledger)

    assert [finding.status for finding in report.findings] == [
        NumericCheckStatus.VERIFIED,
        NumericCheckStatus.VERIFIED,
    ]


def test_unsigned_percentage_without_direction_does_not_hide_negative_sign() -> None:
    ledger = _comparison_ledger()
    report = NumericVerifier().verify(
        _verification("The percentage change was 35.58%."), ledger
    )

    assert report.findings[0].status is NumericCheckStatus.MISMATCH


def test_absolute_change_is_checked_against_recalculated_difference() -> None:
    ledger = _comparison_ledger()
    correct = NumericVerifier().verify(
        _verification("Revenue decreased by 9,250."), ledger
    )
    wrong = NumericVerifier().verify(
        _verification("Revenue decreased by 8,000."), ledger
    )

    assert correct.findings[0].status is NumericCheckStatus.VERIFIED
    assert correct.findings[0].expected_values == [-9250.0]
    assert wrong.findings[0].status is NumericCheckStatus.MISMATCH


def test_metric_values_from_grouped_rows_can_be_checked() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "group_metric",
        {"dimension_col": "product", "metric_col": "revenue"},
        {
            "status": "ok",
            "dimension_col": "product",
            "metric_col": "revenue",
            "rows": [
                {"product": "Laptop", "revenue": 34800.0},
                {"product": "Keyboard", "revenue": 4200.0},
            ],
        },
        mode="direct",
    )
    report = NumericVerifier().verify(
        _verification("Laptop revenue was 34,800."), ledger
    )

    assert report.status is NumericVerificationStatus.PASSED
    assert report.findings[0].status is NumericCheckStatus.VERIFIED


def test_numeric_claim_without_comparable_evidence_is_not_checkable() -> None:
    ledger = EvidenceLedger()
    ledger.add("profile_dataset", {}, {"row_count": 8}, mode="preflight")
    report = NumericVerifier().verify(
        _verification("Revenue decreased by 35%."), ledger
    )

    assert report.status is NumericVerificationStatus.ISSUES_FOUND
    assert report.findings[0].status is NumericCheckStatus.NOT_CHECKABLE


def test_non_numeric_claim_does_not_create_a_numeric_finding() -> None:
    ledger = _comparison_ledger()
    report = NumericVerifier().verify(
        _verification("Revenue decreased during the latest month."), ledger
    )

    assert report.status is NumericVerificationStatus.NOT_APPLICABLE
    assert report.findings == []


@dataclass
class FakeResponse:
    output_text: str


class FakeResponses:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text

    def create(self, **kwargs):
        return FakeResponse(self.output_text)


class FakeClient:
    def __init__(self, output_text: str) -> None:
        self.responses = FakeResponses(output_text)


def test_critic_downgrades_pass_when_numeric_verifier_finds_mismatch() -> None:
    ledger = _comparison_ledger()
    payload = {
        "verification": {
            "summary": "Reviewed.",
            "claims": [
                {
                    "claim_id": "C001",
                    "claim": "Revenue decreased by 30%.",
                    "status": "VERIFIED",
                    "evidence_ids": ["E0001"],
                    "explanation": "Model says supported.",
                    "severity": "low",
                }
            ],
        },
        "critic": {
            "decision": "PASS",
            "summary": "Looks fine.",
            "issues": [],
            "revision_instructions": [],
        },
    }
    verification, critic = CriticVerifier(
        FakeClient(json.dumps(payload)), "test-model"
    ).review(
        question="Did revenue fall?",
        draft_answer="Revenue decreased by 30%.",
        evidence=ledger,
    )

    assert verification.numeric_report is not None
    assert verification.numeric_report.status is NumericVerificationStatus.ISSUES_FOUND
    assert verification.claims[0].status is ClaimStatus.CONTRADICTED
    assert verification.overall_status is VerificationStatus.FAILED
    assert critic.decision is CriticDecision.NEEDS_REVISION
    assert any(issue.issue_type == "numeric_mismatch" for issue in critic.issues)


def test_numeric_report_serializes_inside_verification_report() -> None:
    ledger = _comparison_ledger()
    report = NumericVerifier().verify(
        _verification("Revenue decreased by 35.58%."), ledger
    )
    verification = _verification("Revenue decreased by 35.58%.")
    verification.numeric_report = report

    assert verification.to_dict()["numeric_report"]["status"] == "PASSED"
    assert verification.to_dict()["numeric_report"]["findings"][0]["status"] == "VERIFIED"


def test_grouped_metric_value_must_match_the_named_product() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "group_metric",
        {"dimension_col": "product", "metric_col": "revenue"},
        {
            "status": "ok",
            "dimension_col": "product",
            "metric_col": "revenue",
            "rows": [
                {"product": "Laptop", "revenue": 34800.0},
                {"product": "Keyboard", "revenue": 4200.0},
            ],
        },
        mode="direct",
    )

    correct = NumericVerifier().verify(
        _verification("Laptop revenue was 34,800."), ledger
    )
    wrong_subject = NumericVerifier().verify(
        _verification("Keyboard revenue was 34,800."), ledger
    )

    assert correct.findings[0].status is NumericCheckStatus.VERIFIED
    assert correct.findings[0].matched_subject == "Laptop"
    assert wrong_subject.findings[0].status is NumericCheckStatus.MISMATCH
    assert wrong_subject.findings[0].matched_subject == "Keyboard"
    assert wrong_subject.findings[0].expected_values == [4200.0]


def test_metric_name_binding_prevents_matching_profit_to_revenue() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "revenue"},
        {"status": "ok", "metric_col": "revenue", "previous": 26000.0, "current": 16750.0},
        mode="direct",
    )
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "profit"},
        {"status": "ok", "metric_col": "profit", "previous": 100.0, "current": 120.0},
        mode="direct",
    )
    verification = _verification("Revenue decreased by 20%.", "E0001")
    verification.claims[0].evidence_ids.append("E0002")

    report = NumericVerifier().verify(verification, ledger)

    assert report.findings[0].status is NumericCheckStatus.MISMATCH
    assert report.findings[0].matched_metric == "revenue"
    assert report.findings[0].expected_values == [-35.57692307692308]


def test_numeric_claim_with_multiple_cited_metrics_and_no_metric_name_is_ambiguous() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "revenue"},
        {"status": "ok", "metric_col": "revenue", "previous": 26000.0, "current": 16750.0},
        mode="direct",
    )
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "profit"},
        {"status": "ok", "metric_col": "profit", "previous": 100.0, "current": 120.0},
        mode="direct",
    )
    verification = _verification("The percentage change was 20%.", "E0001")
    verification.claims[0].evidence_ids.append("E0002")

    report = NumericVerifier().verify(verification, ledger)

    assert report.findings[0].status is NumericCheckStatus.AMBIGUOUS
    assert "multiple metrics" in report.findings[0].explanation


def test_period_metric_value_is_bound_to_named_month() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "period_metric",
        {"date_col": "date", "metric_col": "revenue"},
        {
            "status": "ok",
            "date_col": "date",
            "metric_col": "revenue",
            "rows": [
                {"date": "2026-07-01T00:00:00", "revenue": 26000.0},
                {"date": "2026-08-01T00:00:00", "revenue": 16750.0},
            ],
        },
        mode="direct",
    )

    correct = NumericVerifier().verify(
        _verification("August revenue was 16,750."), ledger
    )
    wrong_month = NumericVerifier().verify(
        _verification("August revenue was 26,000."), ledger
    )

    assert correct.findings[0].status is NumericCheckStatus.VERIFIED
    assert correct.findings[0].matched_subject == "2026-08-01T00:00:00"
    assert wrong_month.findings[0].status is NumericCheckStatus.MISMATCH
    assert wrong_month.findings[0].expected_values == [16750.0]


def test_row_count_is_not_confused_with_column_count() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "profile_dataset",
        {},
        {"row_count": 8, "column_count": 5},
        mode="preflight",
    )

    correct = NumericVerifier().verify(
        _verification("The dataset has 8 rows."), ledger
    )
    wrong = NumericVerifier().verify(
        _verification("The dataset has 8 columns."), ledger
    )

    assert correct.findings[0].status is NumericCheckStatus.VERIFIED
    assert wrong.findings[0].status is NumericCheckStatus.MISMATCH
    assert wrong.findings[0].expected_values == [5.0]


def test_critic_downgrades_pass_when_numeric_binding_is_ambiguous() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "revenue"},
        {"status": "ok", "metric_col": "revenue", "previous": 26000.0, "current": 16750.0},
        mode="direct",
    )
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "profit"},
        {"status": "ok", "metric_col": "profit", "previous": 100.0, "current": 120.0},
        mode="direct",
    )
    payload = {
        "verification": {
            "summary": "Reviewed.",
            "claims": [
                {
                    "claim_id": "C001",
                    "claim": "The percentage change was 20%.",
                    "status": "VERIFIED",
                    "evidence_ids": ["E0001", "E0002"],
                    "explanation": "Model says supported.",
                    "severity": "low",
                }
            ],
        },
        "critic": {
            "decision": "PASS",
            "summary": "Looks fine.",
            "issues": [],
            "revision_instructions": [],
        },
    }

    verification, critic = CriticVerifier(
        FakeClient(json.dumps(payload)), "test-model"
    ).review(
        question="What changed?",
        draft_answer="The percentage change was 20%.",
        evidence=ledger,
    )

    assert verification.numeric_report is not None
    assert verification.numeric_report.findings[0].status is NumericCheckStatus.AMBIGUOUS
    assert verification.claims[0].status is ClaimStatus.NOT_VERIFIABLE
    assert critic.decision is CriticDecision.NEEDS_REVISION
    assert any(issue.issue_type == "numeric_ambiguous" for issue in critic.issues)


def test_grouped_metric_value_without_a_named_subject_is_ambiguous() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "group_metric",
        {"dimension_col": "product", "metric_col": "revenue"},
        {
            "status": "ok",
            "dimension_col": "product",
            "metric_col": "revenue",
            "rows": [
                {"product": "Laptop", "revenue": 34800.0},
                {"product": "Keyboard", "revenue": 4200.0},
            ],
        },
        mode="direct",
    )

    report = NumericVerifier().verify(
        _verification("Revenue was 4,200."), ledger
    )

    assert report.findings[0].status is NumericCheckStatus.AMBIGUOUS
    assert "multiple subjects" in report.findings[0].explanation


def test_shared_metric_suffix_does_not_collapse_distinct_columns() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "gross_profit"},
        {"status": "ok", "metric_col": "gross_profit", "previous": 100.0, "current": 120.0},
        mode="direct",
    )
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "net_profit"},
        {"status": "ok", "metric_col": "net_profit", "previous": 200.0, "current": 230.0},
        mode="direct",
    )
    verification = _verification("Profit increased by 20%.", "E0001")
    verification.claims[0].evidence_ids.append("E0002")

    ambiguous = NumericVerifier().verify(verification, ledger)
    verification.claims[0].claim = "Gross profit increased by 20%."
    exact = NumericVerifier().verify(verification, ledger)

    assert ambiguous.findings[0].status is NumericCheckStatus.AMBIGUOUS
    assert exact.findings[0].status is NumericCheckStatus.VERIFIED
    assert exact.findings[0].matched_metric == "gross_profit"


def test_comparison_endpoint_value_requires_previous_or_current_context() -> None:
    ledger = _comparison_ledger()

    current = NumericVerifier().verify(
        _verification("Current revenue was 16,750."), ledger
    )
    no_period = NumericVerifier().verify(
        _verification("Revenue was 16,750."), ledger
    )
    unsupported_month = NumericVerifier().verify(
        _verification("August revenue was 16,750."), ledger
    )

    assert current.findings[0].status is NumericCheckStatus.VERIFIED
    assert current.findings[0].matched_subject == "current period"
    assert no_period.findings[0].status is NumericCheckStatus.AMBIGUOUS
    assert unsupported_month.findings[0].status is NumericCheckStatus.AMBIGUOUS


def test_vietnamese_metric_alias_can_bind_to_english_column_name() -> None:
    from insightpilot.verification.numeric import _extract_mentions

    ledger = _comparison_ledger()
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "profit"},
        {"status": "ok", "metric_col": "profit", "previous": 100.0, "current": 120.0},
        mode="direct",
    )
    verification = _verification("Doanh thu giảm 35,58%.", "E0001")
    verification.claims[0].evidence_ids.append("E0002")

    report = NumericVerifier().verify(verification, ledger)

    assert _extract_mentions("Doanh thu giảm 35,58%.")[0].kind == "percentage_change"
    assert report.findings[0].status is NumericCheckStatus.VERIFIED
    assert report.findings[0].matched_metric == "revenue"


def test_numeric_classification_does_not_borrow_count_context_from_next_clause() -> None:
    from insightpilot.verification.numeric import _extract_mentions

    mentions = _extract_mentions("Revenue was 4,200, while row count was 8.")

    assert [mention.kind for mention in mentions] == ["metric_value", "count"]


def test_claim_for_metric_missing_from_evidence_cannot_borrow_only_available_metric() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "group_metric",
        {"dimension_col": "product", "metric_col": "revenue"},
        {
            "status": "ok",
            "dimension_col": "product",
            "metric_col": "revenue",
            "rows": [{"product": "Laptop", "revenue": 34800.0}],
        },
        mode="direct",
    )

    report = NumericVerifier().verify(
        _verification("Laptop profit was 34,800."), ledger
    )

    assert report.findings[0].status is NumericCheckStatus.NOT_CHECKABLE
    assert "metric not found" in report.findings[0].explanation


def test_claim_for_subject_absent_from_single_row_evidence_is_not_verified() -> None:
    ledger = EvidenceLedger()
    ledger.add(
        "group_metric",
        {"dimension_col": "product", "metric_col": "revenue"},
        {
            "status": "ok",
            "dimension_col": "product",
            "metric_col": "revenue",
            "rows": [{"product": "Laptop", "revenue": 34800.0}],
        },
        mode="direct",
    )

    report = NumericVerifier().verify(
        _verification("Keyboard revenue was 34,800."), ledger
    )

    assert report.findings[0].status is NumericCheckStatus.NOT_CHECKABLE
    assert "subject not found" in report.findings[0].explanation
