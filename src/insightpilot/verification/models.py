from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ClaimStatus(str, Enum):
    """Kết quả xác minh của một khẳng định trong câu trả lời nháp."""

    VERIFIED = "VERIFIED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"


class VerificationStatus(str, Enum):
    """Kết quả tổng thể sau khi kiểm tra các khẳng định quan trọng trong câu trả lời."""

    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    FAILED = "FAILED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class NumericCheckStatus(str, Enum):
    """Kết quả kiểm tra xác định cho một số liệu được nêu trong khẳng định."""

    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    NOT_CHECKABLE = "NOT_CHECKABLE"
    AMBIGUOUS = "AMBIGUOUS"


class NumericVerificationStatus(str, Enum):
    """Kết quả tổng hợp của các phép kiểm tra số học xác định."""

    PASSED = "PASSED"
    ISSUES_FOUND = "ISSUES_FOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class IssueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CriticDecision(str, Enum):
    """Hành động Critic đề xuất đối với câu trả lời nháp hiện tại."""

    PASS = "PASS"
    NEEDS_REVISION = "NEEDS_REVISION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REVIEW_ERROR = "REVIEW_ERROR"


@dataclass
class ClaimVerification:
    """Kết quả xác minh một khẳng định thực tế hoặc phân tích."""

    claim_id: str
    claim: str
    status: ClaimStatus
    evidence_ids: list[str] = field(default_factory=list)
    explanation: str = ""
    severity: IssueSeverity = IssueSeverity.MEDIUM

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim": self.claim,
            "status": self.status.value,
            "evidence_ids": list(self.evidence_ids),
            "explanation": self.explanation,
            "severity": self.severity.value,
        }


@dataclass
class NumericFinding:
    """Kết quả kiểm tra một số liệu được phát hiện trong khẳng định cần xác minh."""

    claim_id: str
    claim: str
    mention: str
    claimed_value: float
    numeric_kind: str
    status: NumericCheckStatus
    expected_values: list[float] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    source_fields: list[str] = field(default_factory=list)
    matched_metric: str | None = None
    matched_subject: str | None = None
    candidate_count: int = 0
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim": self.claim,
            "mention": self.mention,
            "claimed_value": self.claimed_value,
            "numeric_kind": self.numeric_kind,
            "status": self.status.value,
            "expected_values": list(self.expected_values),
            "evidence_ids": list(self.evidence_ids),
            "source_fields": list(self.source_fields),
            "matched_metric": self.matched_metric,
            "matched_subject": self.matched_subject,
            "candidate_count": self.candidate_count,
            "explanation": self.explanation,
        }


@dataclass
class NumericVerificationReport:
    """Các phát hiện từ kiểm tra số học xác định đối với một câu trả lời nháp."""

    status: NumericVerificationStatus
    findings: list[NumericFinding] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "summary": self.summary,
            "findings": [finding.to_dict() for finding in self.findings],
        }


class ClaimSegmentStatus(str, Enum):
    """Trạng thái bao phủ của một phát biểu trong câu trả lời nháp."""

    COVERED = "COVERED"
    UNCOVERED = "UNCOVERED"


class ClaimCoverageStatus(str, Enum):
    """Kết quả tổng thể khi rà soát độ bao phủ của các phát biểu."""

    COMPLETE = "COMPLETE"
    GAPS_FOUND = "GAPS_FOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class ClaimCoverageFinding:
    """Kết quả rà soát một phát biểu có thể chứa thông tin quan trọng."""

    segment_id: str
    statement: str
    status: ClaimSegmentStatus
    matched_claim_ids: list[str] = field(default_factory=list)
    coverage_ratio: float = 0.0
    uncovered_tokens: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "statement": self.statement,
            "status": self.status.value,
            "matched_claim_ids": list(self.matched_claim_ids),
            "coverage_ratio": self.coverage_ratio,
            "uncovered_tokens": list(self.uncovered_tokens),
            "explanation": self.explanation,
        }


@dataclass
class ClaimCoverageReport:
    """Báo cáo cho biết các phát biểu quan trọng đã được Critic xem xét hay chưa."""

    status: ClaimCoverageStatus
    statement_count: int = 0
    covered_count: int = 0
    findings: list[ClaimCoverageFinding] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "statement_count": self.statement_count,
            "covered_count": self.covered_count,
            "uncovered_count": self.statement_count - self.covered_count,
            "summary": self.summary,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass
class VerificationReport:
    """Các kết quả xác minh bằng chứng có cấu trúc cho câu trả lời nháp."""

    overall_status: VerificationStatus
    claims: list[ClaimVerification] = field(default_factory=list)
    summary: str = ""
    numeric_report: NumericVerificationReport | None = None
    claim_coverage_report: ClaimCoverageReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "summary": self.summary,
            "claims": [claim.to_dict() for claim in self.claims],
            "numeric_report": (
                self.numeric_report.to_dict() if self.numeric_report is not None else None
            ),
            "claim_coverage_report": (
                self.claim_coverage_report.to_dict()
                if self.claim_coverage_report is not None
                else None
            ),
        }


@dataclass
class CriticIssue:
    """Một vấn đề được phát hiện trong câu trả lời nháp khi Critic rà soát."""

    issue_type: str
    description: str
    related_claim_id: str | None = None
    severity: IssueSeverity = IssueSeverity.MEDIUM

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_type": self.issue_type,
            "description": self.description,
            "related_claim_id": self.related_claim_id,
            "severity": self.severity.value,
        }


@dataclass
class CriticReport:
    """Quyết định và phản hồi có thể thực hiện đối với câu trả lời nháp."""

    decision: CriticDecision
    summary: str = ""
    issues: list[CriticIssue] = field(default_factory=list)
    revision_instructions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "summary": self.summary,
            "issues": [issue.to_dict() for issue in self.issues],
            "revision_instructions": list(self.revision_instructions),
        }
