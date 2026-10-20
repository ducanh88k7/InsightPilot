from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from insightpilot.verification import (
    ClaimStatus,
    CriticDecision,
    CriticVerifier,
    EvidenceLedger,
    VerificationStatus,
)


@dataclass
class FakeResponse:
    output_text: str


class FakeResponses:
    def __init__(self, output_text: str = "") -> None:
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self.output_text)


class FakeClient:
    def __init__(self, output_text: str = "") -> None:
        self.responses = FakeResponses(output_text)


def make_payload(evidence_ids: list[str], status: str = "VERIFIED") -> dict:
    return {
        "verification": {
            "summary": "Evidence review summary.",
            "claims": [
                {
                    "claim_id": "C001",
                    "claim": "Revenue fell by 35.58%.",
                    "status": status,
                    "evidence_ids": evidence_ids,
                    "explanation": "Reviewed against tool output.",
                    "severity": "low",
                }
            ],
        },
        "critic": {
            "decision": "PASS",
            "summary": "Review complete.",
            "issues": [],
            "revision_instructions": [],
        },
    }


def test_critic_sends_no_tools_and_requests_structured_output():
    ledger = EvidenceLedger()
    ledger.add("compare_last_two_periods", {}, {"percentage_change": -35.58}, mode="direct")
    fake = FakeClient(json.dumps(make_payload(["E0001"])))

    verification, critic = CriticVerifier(fake, "test-model").review(
        question="Did revenue fall?",
        draft_answer="Revenue fell by 35.58%.",
        evidence=ledger,
    )

    assert verification.overall_status is VerificationStatus.VERIFIED
    assert critic.decision is CriticDecision.PASS
    assert fake.responses.calls[0]["tools"] == []
    assert fake.responses.calls[0]["text"]["format"]["name"] == "critic_review"


def test_unknown_evidence_id_cannot_support_verified_claim():
    ledger = EvidenceLedger()
    ledger.add("compare_last_two_periods", {}, {"percentage_change": -35.58}, mode="direct")
    payload = make_payload(["E9999"])
    fake = FakeClient(json.dumps(payload))

    verification, critic = CriticVerifier(fake, "test-model").review(
        question="Did revenue fall?",
        draft_answer="Revenue fell by 35.58%.",
        evidence=ledger,
    )

    claim = verification.claims[0]
    assert claim.status is ClaimStatus.NOT_VERIFIABLE
    assert claim.evidence_ids == []
    assert verification.overall_status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert critic.decision is CriticDecision.NEEDS_REVISION


def test_failed_tool_result_cannot_be_used_as_verified_evidence():
    ledger = EvidenceLedger()
    ledger.add(
        "compare_last_two_periods",
        {},
        {"status": "error", "message": "missing date column"},
        mode="direct",
    )
    fake = FakeClient(json.dumps(make_payload(["E0001"])))

    verification, critic = CriticVerifier(fake, "test-model").review(
        question="Did revenue fall?",
        draft_answer="Revenue fell by 35.58%.",
        evidence=ledger,
    )

    assert verification.overall_status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert verification.claims == []  # Không có bằng chứng thành công nên dừng an toàn, không yêu cầu mô hình tạo claim.
    assert critic.decision is CriticDecision.INSUFFICIENT_EVIDENCE
    assert fake.responses.calls == []  # Không có bằng chứng thành công nên dừng an toàn mà không gọi API.


def test_no_successful_evidence_uses_deterministic_insufficient_report():
    ledger = EvidenceLedger()
    ledger.add("tool", {}, {"status": "error"}, mode="direct")
    fake = FakeClient("not used")

    verification, critic = CriticVerifier(fake, "test-model").review(
        question="Calculate revenue",
        draft_answer="Revenue is 100.",
        evidence=ledger,
    )

    assert verification.overall_status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert critic.decision is CriticDecision.INSUFFICIENT_EVIDENCE
    assert not fake.responses.calls


def test_invalid_json_from_critic_is_reported_as_error():
    ledger = EvidenceLedger()
    ledger.add("tool", {}, {"value": 1}, mode="direct")
    fake = FakeClient("not json")

    with pytest.raises(RuntimeError, match="invalid JSON"):
        CriticVerifier(fake, "test-model").review(
            question="What is the value?",
            draft_answer="The value is 1.",
            evidence=ledger,
        )
