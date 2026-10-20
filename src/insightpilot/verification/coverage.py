from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .models import ClaimCoverageFinding, ClaimCoverageReport, ClaimCoverageStatus, ClaimSegmentStatus, VerificationReport


# Những từ chỉ số liệu hoặc kết luận thường cần được đối chiếu với bằng chứng.
_TU_KHOA_NOI_DUNG_QUAN_TRONG = {
    "revenue", "sales", "profit", "loss", "price", "quantity", "amount",
    "total", "average", "mean", "median", "count", "row", "rows",
    "column", "columns", "record", "records", "dataset", "data", "product",
    "increase", "increased", "decrease", "decreased", "rise", "rose", "fall",
    "fell", "decline", "growth", "change", "percentage", "percent", "trend",
    "highest", "lowest", "top", "bottom", "correlation", "cause", "caused",
    "because", "due", "result", "campaign", "advertising", "month", "period",
    "tăng", "tang", "giảm", "giam", "tổng", "tong", "giá", "gia",
    "hàng", "hang", "cột", "cot", "tháng", "thang", "lợi", "loi",
    "nhuận", "nhuan", "nguyên", "nguyen", "nhân", "nhan", "vì", "vi",
}

# Từ tiếng Việt có nghĩa rõ hơn khi đứng thành cụm, tránh bắt nhầm từ đơn như "thu".
_CUM_TU_QUAN_TRONG = (
    "doanh thu", "doanhthu", "lợi nhuận", "loinhuan", "số lượng", "soluong",
    "trung bình", "trungbinh", "bản ghi", "bang ghi", "dữ liệu", "du lieu",
    "dulieu", "sản phẩm", "san pham", "sanpham", "cao nhất", "cao nhat",
    "thấp nhất", "thap nhat", "thay đổi", "thay doi", "thaydoi", "tỷ lệ",
    "ty le", "tyle", "phần trăm", "phan tram", "phantram", "xu hướng",
    "xu huong", "nguyên nhân", "nguyen nhan", "nguyennhan", "quảng cáo",
    "quang cao", "quangcao",
)

# Các từ nối phổ biến không cần phải được bao phủ riêng khi so khớp nội dung.
_TU_DUNG_BO_QUA = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "do", "does", "did", "by", "from", "to", "of",
    "for", "at", "in", "on", "as", "with", "and", "or", "but", "while",
    "whereas", "than", "compared", "over", "under", "during", "that", "this",
    "these", "those", "into", "about", "up", "down", "so", "then", "also",
    "overall", "more", "less", "it", "its", "their", "they", "we", "our",
    "của", "là", "đã", "được", "với", "trong", "ở", "từ", "tới", "cho",
    "các", "những", "một", "và", "nhưng", "còn", "khi", "tại", "theo", "thì",
    "này", "đó", "so", "sánh", "đang", "sẽ", "có", "cũng", "là", "về",
}

# Giữ nguyên một token số (bao gồm dấu thập phân và dấu phần trăm) khi so khớp.
_MAU_TOKEN = re.compile(r"\d+(?:[.,]\d+)*\s*%?|[^\W\d_]+", flags=re.UNICODE)
_MAU_SO = re.compile(r"\d+(?:[.,]\d+)*\s*%?")
_MAU_TACH_CAU = re.compile(r"(?<=[.!?])\s+(?=\S)|\s*;\s*")
_MAU_TACH_MENH_DE = re.compile(
    r"\s+(?:while|whereas|but|however|trong khi|nhưng|còn)\s+",
    flags=re.IGNORECASE,
)


def _chuan_hoa_van_ban(text: str) -> str:
    """Chuẩn hóa chữ để so khớp, không thay đổi ý nghĩa số liệu."""
    text = text.casefold().replace("**", "").replace("__", "")
    text = re.sub(r"[`*_~]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _chuan_hoa_doan_trich(text: str) -> str:
    """Bỏ dấu câu ở hai đầu để các claim trích nguyên văn vẫn khớp mệnh đề."""
    return _chuan_hoa_van_ban(text).strip(" \t\r\n.,;:!?")


def _tach_token_noi_dung(text: str) -> list[str]:
    """Lấy từ và số có ý nghĩa; bỏ qua dấu câu và các từ nối phổ biến."""
    tokens = [token.strip().casefold() for token in _MAU_TOKEN.findall(_chuan_hoa_van_ban(text))]
    return [token for token in tokens if token and token not in _TU_DUNG_BO_QUA]


def _tach_cac_phat_bieu(answer: str) -> list[str]:
    """Tách câu trả lời thành các câu hoặc mệnh đề để rà soát độ bao phủ."""
    statements: list[str] = []
    for line in answer.splitlines():
        line = line.strip()
        if not line or line.startswith("```") or line.startswith("#"):
            # Không kiểm tra dòng trống, hàng tiêu đề và tiêu đề Markdown.
            continue
        line = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|>\s*)", "", line)
        line = line.strip().strip("|").strip()
        if not line or re.fullmatch(r"[-:|\s]+", line):
            continue

        for sentence in _MAU_TACH_CAU.split(line):
            # Tách thêm các mệnh đề đối lập để tránh bỏ sót vế sau của một câu ghép.
            for clause in _MAU_TACH_MENH_DE.split(sentence):
                clause = clause.strip(" \t\r\n|-")
                if clause:
                    statements.append(clause)
    return statements


def _la_phat_bieu_can_kiem_tra(statement: str) -> bool:
    """Chọn câu có số liệu hoặc từ ngữ thường biểu thị kết luận phân tích."""
    normalized = _chuan_hoa_van_ban(statement)
    if _MAU_SO.search(normalized):
        return True
    tokens = set(_tach_token_noi_dung(normalized))
    if tokens & _TU_KHOA_NOI_DUNG_QUAN_TRONG:
        return True
    return any(phrase in normalized for phrase in _CUM_TU_QUAN_TRONG)


def _chi_so_bao_phu(statement_tokens: list[str], claim_tokens: list[str]) -> tuple[float, list[str]]:
    """Tính tỉ lệ token quan trọng đã được các claim trích dẫn bao phủ."""
    if not statement_tokens:
        return 1.0, []

    available = Counter(claim_tokens)
    missing: list[str] = []
    covered = 0
    for token, count in Counter(statement_tokens).items():
        matched = min(count, available[token])
        covered += matched
        if matched < count:
            missing.extend([token] * (count - matched))
    ratio = covered / sum(Counter(statement_tokens).values())
    return ratio, missing


@dataclass
class ClaimCoverageAuditor:
    """Kiểm tra các phát biểu phân tích quan trọng có được Critic xem xét hay chưa."""

    def audit(self, draft_answer: str, verification: VerificationReport) -> ClaimCoverageReport:
        """So câu trả lời nháp với danh sách claim do Critic trích xuất."""
        candidates = [
            statement
            for statement in _tach_cac_phat_bieu(draft_answer)
            if _la_phat_bieu_can_kiem_tra(statement)
        ]
        if not candidates:
            return ClaimCoverageReport(
                status=ClaimCoverageStatus.NOT_APPLICABLE,
                statement_count=0,
                covered_count=0,
                findings=[],
                summary="Không phát hiện câu số liệu hoặc câu phân tích cần kiểm tra độ bao phủ.",
            )

        claim_tokens = {
            claim.claim_id: _tach_token_noi_dung(claim.claim)
            for claim in verification.claims
        }
        claim_texts = {
            claim.claim_id: _chuan_hoa_doan_trich(claim.claim)
            for claim in verification.claims
        }
        findings: list[ClaimCoverageFinding] = []

        for index, statement in enumerate(candidates, start=1):
            statement_tokens = _tach_token_noi_dung(statement)
            normalized_statement = _chuan_hoa_doan_trich(statement)
            relevant_claim_ids: list[str] = []
            tokens_from_relevant_claims: list[str] = []

            for claim_id, normalized_claim in claim_texts.items():
                if not normalized_claim:
                    continue
                # Claim phải là một đoạn trích nguyên văn hoặc bao gồm nguyên văn phát biểu.
                if (
                    normalized_claim in normalized_statement
                    or normalized_statement in normalized_claim
                ):
                    relevant_claim_ids.append(claim_id)
                    tokens_from_relevant_claims.extend(claim_tokens[claim_id])

            ratio, missing_tokens = _chi_so_bao_phu(
                statement_tokens,
                tokens_from_relevant_claims,
            )
            covered = ratio >= 1.0 and bool(relevant_claim_ids)
            finding_status = ClaimSegmentStatus.COVERED if covered else ClaimSegmentStatus.UNCOVERED
            if covered:
                explanation = "Các token nội dung của phát biểu đã được bao phủ bởi claim được Critic trích xuất."
            else:
                explanation = (
                    "Phát biểu có nội dung phân tích nhưng chưa được claim nào bao phủ đầy đủ. "
                    "Cần xác minh riêng hoặc loại bỏ phát biểu này."
                )

            findings.append(
                ClaimCoverageFinding(
                    segment_id=f"S{index:03d}",
                    statement=statement,
                    status=finding_status,
                    matched_claim_ids=relevant_claim_ids,
                    coverage_ratio=round(ratio, 4),
                    uncovered_tokens=missing_tokens,
                    explanation=explanation,
                )
            )

        covered_count = sum(
            finding.status is ClaimSegmentStatus.COVERED for finding in findings
        )
        uncovered_count = len(findings) - covered_count
        if uncovered_count:
            status = ClaimCoverageStatus.GAPS_FOUND
            summary = (
                f"Phát hiện {uncovered_count}/{len(findings)} phát biểu quan trọng chưa được "
                "các claim đã trích xuất bao phủ đầy đủ."
            )
        else:
            status = ClaimCoverageStatus.COMPLETE
            summary = f"Đã bao phủ đủ {covered_count} phát biểu quan trọng được bộ lọc nhận diện."

        return ClaimCoverageReport(
            status=status,
            statement_count=len(findings),
            covered_count=covered_count,
            findings=findings,
            summary=summary,
        )
