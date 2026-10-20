from __future__ import annotations

import json
from dataclasses import dataclass

from insightpilot.verification import (
    ClaimCoverageAuditor,
    ClaimCoverageStatus,
    ClaimStatus,
    ClaimVerification,
    CriticDecision,
    CriticVerifier,
    EvidenceLedger,
    VerificationReport,
    VerificationStatus,
)


@dataclass
class _GiaLapPhanHoi:
    output_text: str


class _GiaLapResponses:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _GiaLapPhanHoi(self.output_text)


class _GiaLapClient:
    def __init__(self, output_text: str) -> None:
        self.responses = _GiaLapResponses(output_text)


def _bao_cao_xac_minh(*claims: str) -> VerificationReport:
    """Tạo báo cáo giả lập để kiểm tra bộ rà soát độ bao phủ độc lập."""
    return VerificationReport(
        overall_status=VerificationStatus.VERIFIED,
        claims=[
            ClaimVerification(
                claim_id=f"C{index:03d}",
                claim=claim,
                status=ClaimStatus.VERIFIED,
                evidence_ids=["E0001"],
            )
            for index, claim in enumerate(claims, start=1)
        ],
    )


def _payload(claim_text: str) -> str:
    """Tạo đầu ra JSON mà trong kiểm thử giả lập model trả về."""
    return json.dumps(
        {
            "verification": {
                "summary": "Đã rà soát claim được cung cấp.",
                "claims": [
                    {
                        "claim_id": "C001",
                        "claim": claim_text,
                        "status": "VERIFIED",
                        "evidence_ids": ["E0001"],
                        "explanation": "Có bằng chứng thành công.",
                        "severity": "low",
                    }
                ],
            },
            "critic": {
                "decision": "PASS",
                "summary": "Rà soát hoàn tất.",
                "issues": [],
                "revision_instructions": [],
            },
        },
        ensure_ascii=False,
    )


def test_phat_hien_phat_bieu_nguyen_nhan_bi_bo_ngoai_claim() -> None:
    """Phát biểu về nguyên nhân phải được xét riêng, không chỉ kiểm tra con số."""
    answer = (
        "Revenue decreased by 35.58%. "
        "The advertising campaign caused the decline."
    )
    report = ClaimCoverageAuditor().audit(
        answer,
        _bao_cao_xac_minh("Revenue decreased by 35.58%."),
    )

    assert report.status is ClaimCoverageStatus.GAPS_FOUND
    assert report.statement_count == 2
    assert report.covered_count == 1
    assert report.findings[1].status.value == "UNCOVERED"
    assert "campaign" in report.findings[1].uncovered_tokens


def test_hai_menh_de_duoc_bao_phu_khi_ca_hai_claim_da_duoc_trich_xuat() -> None:
    """Không báo thiếu khi mỗi mệnh đề quan trọng đều có claim tương ứng."""
    answer = "Revenue decreased by 35.58%, while profit increased by 20%."
    report = ClaimCoverageAuditor().audit(
        answer,
        _bao_cao_xac_minh(
            "Revenue decreased by 35.58%.",
            "profit increased by 20%.",
        ),
    )

    assert report.status is ClaimCoverageStatus.COMPLETE
    assert report.statement_count == report.covered_count == 2


def test_bo_qua_tieu_de_va_cau_dan_nhap_khong_mang_ket_luan() -> None:
    """Tiêu đề và câu dẫn nhập không được tính như claim dữ liệu bị thiếu."""
    answer = "# Revenue analysis\nHere is the summary.\nRevenue decreased by 35.58%."
    report = ClaimCoverageAuditor().audit(
        answer,
        _bao_cao_xac_minh("Revenue decreased by 35.58%."),
    )

    assert report.status is ClaimCoverageStatus.COMPLETE
    assert report.statement_count == 1


def test_critic_khong_duoc_pass_khi_bo_sot_claim_quan_trong() -> None:
    """Critic phải yêu cầu sửa khi draft có một kết luận chưa được trích xuất."""
    ledger = EvidenceLedger()
    ledger.add(
        "compare_last_two_periods",
        {"metric_col": "revenue"},
        {"status": "ok", "previous": 26000.0, "current": 16750.0},
        mode="direct",
    )
    answer = "Revenue decreased by 35.58%. The advertising campaign caused the decline."
    fake = _GiaLapClient(_payload("Revenue decreased by 35.58%."))

    verification, critic = CriticVerifier(fake, "test-model").review(
        question="Summarize the change.",
        draft_answer=answer,
        evidence=ledger,
    )

    assert verification.claim_coverage_report is not None
    assert verification.claim_coverage_report.status is ClaimCoverageStatus.GAPS_FOUND
    assert critic.decision is CriticDecision.NEEDS_REVISION
    assert any(issue.issue_type == "claim_coverage_gap" for issue in critic.issues)
    assert verification.overall_status is VerificationStatus.PARTIALLY_VERIFIED


def test_bao_cao_do_bao_phu_duoc_chuyen_sang_dict() -> None:
    """Kết quả bao phủ phải có thể đưa vào AgentResult và log JSON."""
    report = ClaimCoverageAuditor().audit(
        "Revenue decreased by 35.58%.",
        _bao_cao_xac_minh("Revenue decreased by 35.58%."),
    )

    output = report.to_dict()
    assert output["status"] == "COMPLETE"
    assert output["statement_count"] == 1
    assert output["uncovered_count"] == 0


def test_khong_ap_dung_khi_cau_tra_loi_khong_co_phat_bieu_phan_tich() -> None:
    """Báo cáo phải phân biệt không cần kiểm tra với kiểm tra bị thất bại."""
    report = ClaimCoverageAuditor().audit(
        "Here is a short introduction.",
        _bao_cao_xac_minh("Here is a short introduction."),
    )

    assert report.status is ClaimCoverageStatus.NOT_APPLICABLE
    assert report.statement_count == 0


def test_report_bao_cao_so_token_con_lai_de_de_truy_vet() -> None:
    """Báo cáo lưu lại từ chưa được bao phủ để hỗ trợ debug và revision."""
    report = ClaimCoverageAuditor().audit(
        "Revenue decreased by 35.58%. The advertising campaign caused the decline.",
        _bao_cao_xac_minh("Revenue decreased by 35.58%."),
    )

    gap = report.findings[1].to_dict()
    assert gap["status"] == "UNCOVERED"
    assert gap["coverage_ratio"] == 0.0
    assert "campaign" in gap["uncovered_tokens"]
    assert report.to_dict()["uncovered_count"] == 1
