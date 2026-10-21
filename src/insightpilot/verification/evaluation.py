from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .coverage import ClaimCoverageAuditor
from .evidence import EvidenceLedger
from .models import (
    ClaimCoverageStatus,
    ClaimStatus,
    ClaimVerification,
    IssueSeverity,
    NumericVerificationStatus,
    VerificationReport,
    VerificationStatus,
)
from .numeric import NumericVerifier

LoaiBoKiemTra = Literal["coverage", "numeric"]


@dataclass(frozen=True)
class EvaluationCase:
    """Một tình huống chuẩn có kết quả mong đợi để đánh giá bộ xác minh."""

    case_id: str
    component: LoaiBoKiemTra
    description: str
    draft_answer: str
    claims: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    expected_issue: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluationCase":
        """Tạo tình huống từ dữ liệu JSON và kiểm tra các trường bắt buộc."""
        component = data.get("component")
        if component not in {"coverage", "numeric"}:
            raise ValueError(f"Thành phần đánh giá không hợp lệ: {component!r}")

        case_id = data.get("case_id")
        description = data.get("description")
        draft_answer = data.get("draft_answer")
        claims = data.get("claims", [])
        evidence = data.get("evidence", [])
        expected_issue = data.get("expected_issue")

        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("case_id phải là chuỗi không rỗng.")
        if not isinstance(description, str):
            raise ValueError(f"{case_id}: description phải là chuỗi.")
        if not isinstance(draft_answer, str):
            raise ValueError(f"{case_id}: draft_answer phải là chuỗi.")
        if not isinstance(claims, list) or not isinstance(evidence, list):
            raise ValueError(f"{case_id}: claims và evidence phải là danh sách.")
        if not isinstance(expected_issue, bool):
            raise ValueError(f"{case_id}: expected_issue phải là true hoặc false.")
        for index, claim in enumerate(claims, start=1):
            if not isinstance(claim, dict) or not isinstance(claim.get("claim"), str):
                raise ValueError(f"{case_id}: claim thứ {index} phải có trường claim dạng chuỗi.")
            evidence_ids = claim.get("evidence_ids", [])
            if not isinstance(evidence_ids, list) or not all(isinstance(item, str) for item in evidence_ids):
                raise ValueError(f"{case_id}: evidence_ids của claim thứ {index} phải là danh sách chuỗi.")
        for index, item in enumerate(evidence, start=1):
            if not isinstance(item, dict) or not isinstance(item.get("tool_name"), str):
                raise ValueError(f"{case_id}: evidence thứ {index} phải có tool_name dạng chuỗi.")
            if not isinstance(item.get("result"), dict):
                raise ValueError(f"{case_id}: result của evidence thứ {index} phải là dictionary.")
            if not isinstance(item.get("arguments", {}), dict):
                raise ValueError(f"{case_id}: arguments của evidence thứ {index} phải là dictionary.")

        return cls(
            case_id=case_id,
            component=component,
            description=description,
            draft_answer=draft_answer,
            claims=claims,
            evidence=evidence,
            expected_issue=expected_issue,
        )


@dataclass(frozen=True)
class EvaluationCaseResult:
    """Kết quả dự đoán của một tình huống so với nhãn chuẩn."""

    case_id: str
    component: str
    description: str
    expected_issue: bool
    detected_issue: bool
    actual_status: str
    passed: bool
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Chuyển kết quả thành dictionary phục vụ hiển thị hoặc lưu JSON."""
        return asdict(self)


@dataclass(frozen=True)
class ClassificationMetrics:
    """Các chỉ số đánh giá cho bài toán phát hiện có vấn đề hay không."""

    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0

    @property
    def precision(self) -> float:
        """Tỷ lệ cảnh báo đúng trong tất cả trường hợp hệ thống đã cảnh báo."""
        tong = self.true_positive + self.false_positive
        return self.true_positive / tong if tong else 0.0

    @property
    def recall(self) -> float:
        """Tỷ lệ vấn đề thật được phát hiện trong tất cả vấn đề thật."""
        tong = self.true_positive + self.false_negative
        return self.true_positive / tong if tong else 0.0

    @property
    def f1(self) -> float:
        """Điểm F1 cân bằng precision và recall."""
        tong = self.precision + self.recall
        return 2 * self.precision * self.recall / tong if tong else 0.0

    @property
    def accuracy(self) -> float:
        """Tỷ lệ dự đoán đúng trên toàn bộ tình huống."""
        tong = (
            self.true_positive
            + self.false_positive
            + self.true_negative
            + self.false_negative
        )
        return (self.true_positive + self.true_negative) / tong if tong else 0.0

    def to_dict(self) -> dict[str, int | float]:
        """Trả số đếm và chỉ số dạng số để có thể serialize sang JSON."""
        return {
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "accuracy": round(self.accuracy, 4),
        }


@dataclass
class VerificationEvaluationReport:
    """Báo cáo tổng hợp các tình huống đánh giá và chỉ số theo từng thành phần."""

    results: list[EvaluationCaseResult] = field(default_factory=list)
    overall: ClassificationMetrics = field(default_factory=ClassificationMetrics)
    by_component: dict[str, ClassificationMetrics] = field(default_factory=dict)

    @property
    def passed_count(self) -> int:
        """Đếm số tình huống có dự đoán trùng với nhãn chuẩn."""
        return sum(result.passed for result in self.results)

    @property
    def failed_count(self) -> int:
        """Đếm số tình huống có dự đoán khác với nhãn chuẩn."""
        return len(self.results) - self.passed_count

    def to_dict(self) -> dict[str, Any]:
        """Chuyển toàn bộ báo cáo sang dictionary có thể lưu thành JSON."""
        return {
            "case_count": len(self.results),
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "overall": self.overall.to_dict(),
            "by_component": {
                ten: metrics.to_dict()
                for ten, metrics in self.by_component.items()
            },
            "results": [result.to_dict() for result in self.results],
        }


def load_evaluation_cases(path: str | Path) -> list[EvaluationCase]:
    """Đọc bộ tình huống JSON, đồng thời phát hiện ID bị lặp."""
    duong_dan = Path(path)
    with duong_dan.open("r", encoding="utf-8") as tep:
        payload = json.load(tep)

    if not isinstance(payload, list):
        raise ValueError("Tệp đánh giá phải chứa một danh sách tình huống JSON.")

    if not all(isinstance(item, dict) for item in payload):
        raise ValueError("Mỗi phần tử trong tệp đánh giá phải là một đối tượng JSON.")

    cases = [EvaluationCase.from_dict(item) for item in payload]
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Bộ dữ liệu đánh giá có case_id bị trùng.")
    return cases


def _tao_ledger(evidence_data: list[dict[str, Any]]) -> EvidenceLedger:
    """Tạo ledger mới từ bằng chứng được mô tả trong một tình huống đánh giá."""
    ledger = EvidenceLedger()
    for item in evidence_data:
        ledger.add(
            tool_name=item["tool_name"],
            arguments=item.get("arguments", {}),
            result=item["result"],
            mode=item.get("mode", "evaluation"),
            plan_step_id=item.get("plan_step_id"),
            execution_status=item.get("execution_status"),
        )
    return ledger


def _tao_verification(case: EvaluationCase) -> VerificationReport:
    """Chuyển claim trong bộ dữ liệu thành báo cáo để kiểm tra độc lập từng thành phần."""
    claims: list[ClaimVerification] = []
    for index, data in enumerate(case.claims, start=1):
        claims.append(
            ClaimVerification(
                claim_id=data.get("claim_id", f"C{index:03d}"),
                claim=data["claim"],
                status=ClaimStatus(data.get("status", "VERIFIED")),
                evidence_ids=list(data.get("evidence_ids", [])),
                explanation=data.get("explanation", "Nhãn chuẩn của bộ đánh giá."),
                severity=IssueSeverity(data.get("severity", "medium")),
            )
        )
    return VerificationReport(
        overall_status=VerificationStatus.VERIFIED if claims else VerificationStatus.INSUFFICIENT_EVIDENCE,
        claims=claims,
        summary="Báo cáo được dựng từ bộ dữ liệu đánh giá, không gọi LLM.",
    )


def _danh_gia_mot_case(case: EvaluationCase) -> EvaluationCaseResult:
    """Chạy đúng bộ kiểm tra của case và quy đổi kết quả thành cờ có vấn đề."""
    verification = _tao_verification(case)

    if case.component == "coverage":
        report = ClaimCoverageAuditor().audit(case.draft_answer, verification)
        detected_issue = report.status is ClaimCoverageStatus.GAPS_FOUND
    else:
        report = NumericVerifier().verify(verification, _tao_ledger(case.evidence))
        detected_issue = report.status is NumericVerificationStatus.ISSUES_FOUND

    actual_status = report.status.value
    return EvaluationCaseResult(
        case_id=case.case_id,
        component=case.component,
        description=case.description,
        expected_issue=case.expected_issue,
        detected_issue=detected_issue,
        actual_status=actual_status,
        passed=case.expected_issue == detected_issue,
        summary=report.summary,
    )


def _tinh_chi_so(results: list[EvaluationCaseResult]) -> ClassificationMetrics:
    """Tạo ma trận nhầm lẫn và tính precision, recall, F1, accuracy."""
    return ClassificationMetrics(
        true_positive=sum(item.expected_issue and item.detected_issue for item in results),
        false_positive=sum(not item.expected_issue and item.detected_issue for item in results),
        true_negative=sum(not item.expected_issue and not item.detected_issue for item in results),
        false_negative=sum(item.expected_issue and not item.detected_issue for item in results),
    )


def run_verification_evaluation(
    cases: list[EvaluationCase],
) -> VerificationEvaluationReport:
    """Chạy bộ đánh giá cục bộ và tổng hợp số liệu cho mỗi thành phần."""
    case_results = [_danh_gia_mot_case(case) for case in cases]
    components = sorted({result.component for result in case_results})
    by_component = {
        component: _tinh_chi_so(
            [result for result in case_results if result.component == component]
        )
        for component in components
    }
    return VerificationEvaluationReport(
        results=case_results,
        overall=_tinh_chi_so(case_results),
        by_component=by_component,
    )
