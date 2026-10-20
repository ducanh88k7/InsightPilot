from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from dataclasses import dataclass
from typing import Iterable

from .evidence import EvidenceExecutionStatus, EvidenceItem, EvidenceLedger
from .models import (
    ClaimVerification,
    NumericCheckStatus,
    NumericFinding,
    NumericVerificationReport,
    NumericVerificationStatus,
    VerificationReport,
)

# Trước tiên hỗ trợ các cách viết số phổ biến, rõ ràng. Ngày theo định dạng ISO
# được bỏ qua để ngày như 2026-10-20 không bị nhận nhầm thành ba số đo.
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+Z-]+)?\b")
_NUMBER_RE = re.compile(
    r"(?<![\w/])[-+]?(?:"
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|"  # Ví dụ: 1,234 hoặc 1,234.56
    r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|"  # Ví dụ: 1.234 hoặc 1.234,56
    r"\d+[.,]\d+|"                         # Dùng dấu phẩy hoặc dấu chấm làm dấu thập phân
    r"\d+(?!\d|[.,]\d)"                       # Số nguyên, không phải phần đầu của một số dài hơn
    r")\s*(?:%|percent(?:age)?(?:\s+points?)?)?",
    re.IGNORECASE,
)

_PERCENT_WORD_RE = re.compile(r"\bpercent(?:age)?(?:\s+points?)?\b", re.IGNORECASE)
_METRIC_WORD_RE = re.compile(
    r"\b(revenue|sales|turnover|profit|cost|expense|margin|amount|total|average|mean|sum|count|quantity|units?|orders?|customers?|product|metric|percentage|percent|rate|increase|increased|increasing|decrease|decreased|decreasing|decline|declined|drop|dropped|fell|fall|rose|rise|growth|change|changed|value|price|row|rows|records?|columns?)\b"
    r"|doanh\s*thu|doanh\s*số|lợi\s*nhuận|chi\s*phí|số\s*lượng|tăng|giảm|sụt|thay\s*đổi",
    re.IGNORECASE,
)
_PERCENT_CONTEXT_RE = re.compile(r"\b(percent(?:age)?|rate|growth rate)\b", re.IGNORECASE)
_CHANGE_CONTEXT_RE = re.compile(
    r"\b(change|changed|increase|increased|decrease|decreased|decline|declined|drop|dropped|fall|fell|rise|rose|reduced|reduction|grew|growth)\b|thay\s*đổi|tăng|giảm|sụt",
    re.IGNORECASE,
)
_DOWN_CONTEXT_RE = re.compile(
    r"\b(decrease|decreased|decline|declined|drop|dropped|fall|fell|down|lower|reduced|reduction)\b|giảm|sụt|suy\s*giảm",
    re.IGNORECASE,
)
_UP_CONTEXT_RE = re.compile(
    r"\b(increase|increased|growth|grew|rise|rose|up|higher|grew)\b|tăng",
    re.IGNORECASE,
)
_COUNT_CONTEXT_RE = re.compile(r"\b(count|rows?|records?|columns?|items?)\b|số\s*lượng", re.IGNORECASE)
_CURRENCY_RE = re.compile(r"[$€£¥₫]|\b(?:USD|EUR|VND|dollars?|euros?)\b", re.IGNORECASE)
_EXPLICIT_METRIC_CONTEXT_RE = re.compile(
    r"\b(revenue|sales|turnover|profit|earnings|cost|costs|expense|expenses|margin|"
    r"quantity|units?|orders?|customers?|price|rows?|records?|columns?|fields?)\b"
    r"|doanh\s*thu|doanh\s*số|lợi\s*nhuận|chi\s*phí|số\s*lượng|đơn\s*giá|"
    r"giá|hàng|bản\s*ghi|cột",
    re.IGNORECASE,
)
_SUBJECT_STOPWORDS = {
    "a", "an", "the", "is", "was", "were", "are", "be", "been", "has", "have",
    "had", "of", "for", "from", "to", "by", "in", "on", "at", "and", "or",
    "but", "while", "whereas", "with", "during", "this", "that", "these", "those",
    "latest", "current", "previous", "prior", "period", "month", "monthly", "year",
    "dataset", "data", "total", "average", "mean", "sum", "metric", "value", "amount",
    "revenue", "sales", "turnover", "profit", "earnings", "cost", "costs", "expense",
    "expenses", "margin", "quantity", "unit", "units", "order", "orders", "customer",
    "customers", "price", "count", "row", "rows", "record", "records", "column",
    "columns", "field", "fields", "percentage", "percent", "rate", "change", "changed",
    "increase", "increased", "decrease", "decreased", "decline", "declined", "drop", "dropped",
    "fell", "fall", "rose", "rise", "growth", "up", "down", "higher", "lower", "by",
    "tháng", "kỳ", "doanh", "thu", "doanhthu", "doanhso", "lợi", "nhuận", "lợinhuận",
    "chi", "phí", "chiphi", "số", "lượng", "soluong", "tăng", "giảm", "sụt", "thay", "đổi",
    "có", "là", "của", "trong", "so", "với", "dữ", "liệu", "bản", "ghi", "cột", "hàng",
}


@dataclass(frozen=True)
class _NumericMention:
    token: str
    value: float
    kind: str
    context: str
    direction: str | None
    explicit_sign: bool
    decimal_places: int


@dataclass(frozen=True)
class _NumericFact:
    value: float
    kind: str
    evidence_id: str
    source_field: str
    metric_name: str | None = None
    subject: str | None = None
    subject_field: str | None = None


def _parse_number(token: str) -> float:
    """Phân tích các cách hiển thị số thông dụng trong tiếng Anh/tiếng Việt thành số thực."""
    cleaned = re.sub(r"\s*(?:%|percent(?:age)?(?:\s+points?)?)\s*$", "", token, flags=re.I)
    cleaned = cleaned.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        # Dấu phân cách cuối cùng được xem là dấu thập phân.
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        after = cleaned.rsplit(",", 1)[1]
        if len(after) == 3 and after.isdigit():
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    return float(cleaned)


def _number_kind(claim: str, start: int, end: int, token: str) -> str | None:
    """Phân loại số liệu dựa trên mệnh đề chứa nó, không mượn ngữ cảnh của metric bên cạnh."""
    clause_start, clause_end = _clause_bounds(claim, start, end)
    lowered = claim[clause_start:clause_end].lower()
    local_start = start - clause_start
    local_end = end - clause_start
    around = lowered[max(0, local_start - 48): min(len(lowered), local_end + 48)]
    before = lowered[max(0, local_start - 25):local_start]
    token_has_percent = "%" in token or bool(_PERCENT_WORD_RE.search(token))
    if token_has_percent or _PERCENT_CONTEXT_RE.search(around):
        return "percentage_change"

    if _CURRENCY_RE.search(around):
        # Số tiền thường biểu thị giá trị của metric, trừ khi số tiền được
        # mô tả rõ là mức chênh lệch.
        if _CHANGE_CONTEXT_RE.search(around) and not re.search(r"\b(?:from|to)\b", before):
            return "absolute_change"
        return "metric_value"

    if _COUNT_CONTEXT_RE.search(around):
        return "count"

    if _CHANGE_CONTEXT_RE.search(around):
        # Trong cụm như "from 26,000 to 16,750", hai số là giá trị đầu mút,
        # không phải bản thân mức chênh lệch.
        if re.search(r"\b(?:from|to)\s*$", before):
            return "metric_value"
        if re.search(r"\bby\s*$", before) or re.search(r"\b(?:absolute )?change\b", around):
            return "absolute_change"
        # Động từ chỉ hướng như "revenue fell 9,250" thường diễn đạt mức thay đổi.
        if re.search(r"\b(fell|fall|dropped|declined|increased|rose|grew|giảm|tăng)\b", around):
            return "absolute_change"

    if _METRIC_WORD_RE.search(around):
        return "metric_value"
    return None


def _clause_bounds(claim: str, start: int, end: int) -> tuple[int, int]:
    """Trả về vị trí đầu và cuối của mệnh đề chứa số liệu đang xét."""
    separators = list(
        re.finditer(r"[,;.!?\n]|\b(?:and|while|whereas|but|yet)\b", claim, re.IGNORECASE)
    )
    segment_start = 0
    segment_end = len(claim)
    for separator in separators:
        if separator.end() <= start:
            segment_start = separator.end()
        elif separator.start() >= end:
            segment_end = separator.start()
            break
    return segment_start, segment_end


def _clause_for_span(claim: str, start: int, end: int) -> str:
    """Trả về mệnh đề của một số liệu, tránh lẫn với metric không liên quan ở gần đó."""
    segment_start, segment_end = _clause_bounds(claim, start, end)
    return claim[segment_start:segment_end].strip()

def _direction_for_mention(claim: str, start: int, end: int) -> str | None:
    """Xác định cách diễn đạt tăng/giảm trong chính mệnh đề chứa số liệu."""
    segment_start = 0
    separators = list(
        re.finditer(r"[,;.!?\n]|\b(?:and|while|whereas|but|yet)\b", claim, re.IGNORECASE)
    )
    segment_end = len(claim)
    for separator in separators:
        if separator.end() <= start:
            segment_start = separator.end()
        elif separator.start() >= end:
            segment_end = separator.start()
            break
    segment = claim[segment_start:segment_end]
    local_start = start - segment_start
    prefix = segment[:local_start]
    suffix = segment[local_start:]

    direction_matches: list[tuple[int, str]] = []
    for pattern, direction in ((_DOWN_CONTEXT_RE, "down"), (_UP_CONTEXT_RE, "up")):
        direction_matches.extend(
            (match.end(), direction) for match in pattern.finditer(prefix)
        )
    if direction_matches:
        return max(direction_matches, key=lambda item: item[0])[1]

    suffix_matches: list[tuple[int, str]] = []
    for pattern, direction in ((_DOWN_CONTEXT_RE, "down"), (_UP_CONTEXT_RE, "up")):
        suffix_matches.extend(
            (match.start(), direction) for match in pattern.finditer(suffix)
        )
    if suffix_matches:
        return min(suffix_matches, key=lambda item: item[0])[1]
    return None


def _extract_mentions(claim: str) -> list[_NumericMention]:
    """Trích xuất các số liệu được gắn với ngữ cảnh dữ liệu hoặc metric."""
    masked = _ISO_DATE_RE.sub(lambda match: " " * len(match.group(0)), claim)
    mentions: list[_NumericMention] = []
    for match in _NUMBER_RE.finditer(masked):
        token = match.group(0).strip()
        try:
            value = _parse_number(token)
        except ValueError:
            continue
        if not math.isfinite(value):
            continue
        kind = _number_kind(claim, match.start(), match.end(), token)
        if kind is None:
            continue
        numeric_part = re.sub(r"\s*(?:%|percent(?:age)?(?:\s+points?)?)\s*$", "", token, flags=re.I)
        decimal_places = 0
        if "." in numeric_part and "," in numeric_part:
            decimal_separator = "." if numeric_part.rfind(".") > numeric_part.rfind(",") else ","
            decimal_places = len(numeric_part.rsplit(decimal_separator, 1)[1])
        elif "." in numeric_part:
            decimal_places = len(numeric_part.rsplit(".", 1)[1])
        elif "," in numeric_part:
            tail = numeric_part.rsplit(",", 1)[1]
            if not (len(tail) == 3 and tail.isdigit()):
                decimal_places = len(tail)
        clause_context = _clause_for_span(claim, match.start(), match.end())
        mentions.append(
            _NumericMention(
                token=token,
                value=value,
                kind=kind,
                context=clause_context,
                direction=_direction_for_mention(claim, match.start(), match.end()),
                explicit_sign=token.startswith(('-', '+')),
                decimal_places=decimal_places,
            )
        )
    return mentions


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _fact_kind(path: str) -> str:
    leaf = path.rsplit(".", 1)[-1].lower()
    normalized = leaf.replace("[", "_").replace("]", "_")
    if any(term in normalized for term in ("percentage", "percent", "pct", "rate")):
        return "percentage_change"
    if "absolute_change" in normalized or normalized == "change":
        return "absolute_change"
    if any(term in normalized for term in ("row_count", "num_rows", "column_count", "unique_count", "missing_count", "count", "rows", "columns")):
        return "count"
    return "metric_value"


def _iter_numeric_leaves(value: object, path: str = "result") -> Iterable[tuple[str, float]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield from _iter_numeric_leaves(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_numeric_leaves(child, f"{path}[{index}]")
    else:
        number = _finite_number(value)
        if number is not None:
            yield path, number


def _result_column(item: EvidenceItem, key: str) -> str | None:
    """Tìm tên cột trong kết quả Tool trước, sau đó mới tìm trong tham số gọi Tool."""
    value = item.result.get(key)
    if not isinstance(value, str) or not value:
        value = item.arguments.get(key)
    return value if isinstance(value, str) and value else None


def _normalise_label(value: str) -> str:
    """Chuẩn hóa nhãn để đối chiếu tên metric hoặc chiều phân loại với nội dung khẳng định."""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _label_in_text(label: str, text: str) -> bool:
    """Đối chiếu cả cụm nhãn sau chuẩn hóa, không tự đoán alias ngắn."""
    normalized_label = _normalise_label(label)
    normalized_text = _normalise_label(text)
    if not normalized_label or not normalized_text:
        return False
    return f" {normalized_label} " in f" {normalized_text} "


def _metric_match_quality(metric: str, text: str) -> int | None:
    """Trả về 2 nếu khớp chính xác tên trường, 1 nếu khớp alias được kiểm soát, nếu không trả None."""
    aliases = {
        "row_count": ("row", "rows", "record", "records", "dataset size", "hàng", "bản ghi"),
        "column_count": ("column", "columns", "field", "fields", "cột"),
        "missing_count": ("missing", "missing values", "null values", "giá trị thiếu"),
        "unique_count": ("unique", "unique values", "distinct values", "giá trị duy nhất"),
        "absolute_change": ("absolute change", "amount of change", "mức thay đổi", "mức tăng", "mức giảm"),
        "percentage_change": ("percentage change", "percent change", "percentage", "percent", "phần trăm thay đổi", "tỷ lệ thay đổi"),
        "revenue": ("doanh thu", "doanh số", "sales", "turnover"),
        "sales": ("doanh thu", "doanh số", "revenue", "turnover"),
        "profit": ("lợi nhuận", "earnings"),
        "gross_profit": ("lợi nhuận gộp", "gross profit"),
        "net_profit": ("lợi nhuận ròng", "net profit"),
        "cost": ("chi phí", "expense", "expenses"),
        "quantity": ("số lượng", "units"),
        "price": ("giá", "đơn giá", "unit price"),
    }
    if _label_in_text(metric, text):
        return 2
    if any(_label_in_text(alias, text) for alias in aliases.get(metric.casefold(), ())):
        return 1
    # Cột dữ liệu có tên ghép đôi khi được gọi bằng từ cuối (ví dụ
    # total_revenue -> revenue), nhưng mức ưu tiên thấp hơn tên cột chính xác.
    parts = _normalise_label(metric).split()
    if len(parts) > 1 and _label_in_text(parts[-1], text):
        return 1
    return None


def _subject_for_path(
    item: EvidenceItem,
    path: str,
) -> tuple[str | None, str | None]:
    """Trả về nhãn chiều phân loại/ngày tháng của một giá trị số nằm trong một dòng dữ liệu."""
    match = re.search(r"(?:^|\.)rows\[(\d+)\]", path)
    if not match:
        return None, None
    rows = item.result.get("rows")
    index = int(match.group(1))
    if not isinstance(rows, list) or index >= len(rows) or not isinstance(rows[index], dict):
        return None, None
    row = rows[index]
    dimension_col = _result_column(item, "dimension_col")
    date_col = _result_column(item, "date_col")
    for field_name in (dimension_col, date_col):
        if field_name and row.get(field_name) is not None:
            return str(row[field_name]), field_name

    # Dùng nhãn duy nhất không phải số trong dòng làm phương án dự phòng khi Tool chưa khai báo
    # rõ cột chiều phân loại. Không đoán nếu một dòng có nhiều nhãn.
    excluded = {
        _result_column(item, "metric_col"),
        "value", "count", "row_count", "percentage_change", "absolute_change",
    }
    labels = [
        (key, value)
        for key, value in row.items()
        if key not in excluded and isinstance(value, str) and value.strip()
    ]
    if len(labels) == 1:
        return str(labels[0][1]), str(labels[0][0])
    return None, None


def _facts_for_evidence(item: EvidenceItem) -> list[_NumericFact]:
    """Tạo các dữ kiện số có kiểu, kèm ngữ cảnh metric và dòng/kỳ thời gian."""
    if item.execution_status is not EvidenceExecutionStatus.SUCCESS:
        return []
    if item.result.get("status") == "error":
        return []

    result = item.result
    facts: list[_NumericFact] = []
    metric_name = _result_column(item, "metric_col")
    previous = _finite_number(result.get("previous"))
    current = _finite_number(result.get("current"))
    is_comparison = previous is not None and current is not None

    if is_comparison:
        facts.append(
            _NumericFact(
                previous, "metric_value", item.evidence_id, "previous", metric_name,
                "previous period", "period_role",
            )
        )
        facts.append(
            _NumericFact(
                current, "metric_value", item.evidence_id, "current", metric_name,
                "current period", "period_role",
            )
        )
        absolute_change = current - previous
        facts.append(
            _NumericFact(
                absolute_change, "absolute_change", item.evidence_id,
                "computed(current - previous)", metric_name,
            )
        )
        if previous != 0:
            percentage_change = (absolute_change / previous) * 100.0
            facts.append(
                _NumericFact(
                    percentage_change, "percentage_change", item.evidence_id,
                    "computed((current - previous) / previous * 100)", metric_name,
                )
            )

    for path, number in _iter_numeric_leaves(result):
        leaf = path.rsplit(".", 1)[-1].lower()
        if is_comparison and leaf in {"previous", "current", "absolute_change", "percentage_change"}:
            # Các giá trị suy ra ở trên được tính lại từ hai đầu mút thay vì tin giá trị có sẵn.
            continue
        subject, subject_field = _subject_for_path(item, path)
        leaf_name = path.removeprefix("result.")
        # Với các dòng theo nhóm/kỳ, cột metric đã cấu hình là đại lượng đo
        # ngay cả khi đường dẫn đầu ra nằm bên trong rows[index].
        fact_metric = metric_name
        if fact_metric is None:
            if leaf in {"row_count", "column_count", "unique_count", "missing_count"}:
                fact_metric = leaf
            elif leaf not in {
                "count", "rows", "columns", "previous", "current",
                "absolute_change", "percentage_change",
            }:
                fact_metric = leaf
        facts.append(
            _NumericFact(
                number,
                _fact_kind(path),
                item.evidence_id,
                leaf_name,
                fact_metric,
                subject,
                subject_field,
            )
        )
    return facts


def _subject_aliases(subject: str) -> set[str]:
    """Tạo alias thận trọng cho nhãn dòng, bao gồm ngày và tên tháng."""
    aliases = {subject.strip()}
    try:
        parsed = datetime.fromisoformat(subject.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        aliases.update({
            parsed.strftime("%B"),
            parsed.strftime("%b"),
            f"tháng {parsed.month}",
        })
    normalized_subject = _normalise_label(subject)
    if normalized_subject == "previous period":
        aliases.update({"previous", "prior", "previous period", "prior period", "kỳ trước"})
    elif normalized_subject == "current period":
        aliases.update({"current", "current period", "latest", "latest period", "kỳ hiện tại", "kỳ gần nhất"})
    return {alias for alias in aliases if _normalise_label(alias)}



def _has_unmatched_subject_hint(context: str) -> bool:
    """Trả về True nếu mệnh đề nhắc đến một đối tượng có vẻ không nằm trong các dòng được viện dẫn."""
    without_numbers = _NUMBER_RE.sub(" ", context)
    tokens = _normalise_label(without_numbers).split()
    return any(token not in _SUBJECT_STOPWORDS for token in tokens)

def _filter_facts_for_mention(
    mention: _NumericMention,
    candidates: list[_NumericFact],
) -> tuple[list[_NumericFact], str | None, str | None, str | None]:
    """Gắn một số liệu với metric và chiều phân loại được nêu trong mệnh đề của nó.
        
            Lý do trả về là None nếu có thể tiếp tục đối chiếu; nếu không, nó mô tả sự mơ hồ
            hoặc metric/đối tượng không tìm thấy trong bằng chứng được viện dẫn.
            
        """
    if not candidates:
        return [], None, None, "no_comparable_fact"

    known_metrics = list(dict.fromkeys(
        fact.metric_name for fact in candidates if fact.metric_name
    ))
    metric_qualities = {
        metric: _metric_match_quality(metric, mention.context)
        for metric in known_metrics
    }
    metric_qualities = {
        metric: quality for metric, quality in metric_qualities.items()
        if quality is not None
    }
    if metric_qualities:
        best_quality = max(metric_qualities.values())
        mentioned_metrics = [
            metric for metric, quality in metric_qualities.items()
            if quality == best_quality
        ]
        selected_metrics = {_normalise_label(value) for value in mentioned_metrics}
        if len(selected_metrics) > 1:
            return [], None, None, "ambiguous_metric"
        candidates = [
            fact for fact in candidates
            if fact.metric_name and _normalise_label(fact.metric_name) in selected_metrics
        ]
        matched_metric = mentioned_metrics[0]
    elif known_metrics and _EXPLICIT_METRIC_CONTEXT_RE.search(mention.context):
        # Mệnh đề nêu một khái niệm metric nhưng không trường nào trong bằng chứng được viện dẫn
        # có thể gắn với metric đó. Không âm thầm thay bằng metric duy nhất đang có.
        return [], None, None, "metric_not_found"
    elif len({_normalise_label(value) for value in known_metrics}) > 1:
        return [], None, None, "ambiguous_metric"
    else:
        matched_metric = known_metrics[0] if known_metrics else None

    if not candidates:
        return [], matched_metric, None, "metric_not_found"

    known_subjects = list(dict.fromkeys(
        fact.subject for fact in candidates if fact.subject
    ))
    matched_subjects: list[str] = []
    for subject in known_subjects:
        if any(_label_in_text(alias, mention.context) for alias in _subject_aliases(subject)):
            matched_subjects.append(subject)
    if matched_subjects:
        # Ưu tiên đối tượng cụ thể nhất khi các nhãn chồng lấn (ví dụ Laptop và Gaming Laptop).
        longest = max(len(_normalise_label(value)) for value in matched_subjects)
        matched_subjects = [
            value for value in matched_subjects
            if len(_normalise_label(value)) == longest
        ]
        selected_subjects = {_normalise_label(value) for value in matched_subjects}
        candidates = [
            fact for fact in candidates
            if fact.subject and _normalise_label(fact.subject) in selected_subjects
        ]
        matched_subject = matched_subjects[0] if len(matched_subjects) == 1 else None
    elif len({_normalise_label(value) for value in known_subjects}) > 1:
        return [], matched_metric, None, "ambiguous_subject"
    elif known_subjects and _has_unmatched_subject_hint(mention.context):
        # Khẳng định có vẻ nêu một đối tượng nhưng không dòng nào được viện dẫn chứa đối tượng đó.
        return [], matched_metric, None, "subject_not_found"
    else:
        matched_subject = known_subjects[0] if known_subjects else None

    if not candidates:
        return [], matched_metric, matched_subject, "subject_not_found"
    return candidates, matched_metric, matched_subject, None

def _rounding_tolerance(mention: _NumericMention) -> float:
    """Chấp nhận sai lệch do làm tròn thông thường nhưng không chấp nhận số liệu sai đáng kể."""
    return max(1e-7, 0.5 * (10 ** (-mention.decimal_places)) + 1e-9)


def _direction_matches(mention: _NumericMention, expected: float) -> bool:
    if mention.kind not in {"percentage_change", "absolute_change"}:
        return True
    if mention.direction == "down":
        return expected < 0
    if mention.direction == "up":
        return expected > 0
    return True


def _mention_matches(mention: _NumericMention, fact: _NumericFact) -> bool:
    tolerance = _rounding_tolerance(mention)
    if mention.kind in {"percentage_change", "absolute_change"}:
        if mention.explicit_sign:
            value_matches = abs(mention.value - fact.value) <= tolerance
        elif mention.direction in {"down", "up"}:
            # "decreased by 35.6%" nêu độ lớn; từ ngữ giảm cho biết dấu của mức thay đổi.
            value_matches = abs(abs(mention.value) - abs(fact.value)) <= tolerance
        else:
            # Nếu không có từ chỉ hướng, không tự coi số dương là
            # độ lớn của mức thay đổi âm. Câu trả lời phải ghi dấu hoặc
            # nêu rõ metric tăng hay giảm.
            value_matches = abs(mention.value - fact.value) <= tolerance
        return value_matches and _direction_matches(mention, fact.value)
    return abs(mention.value - fact.value) <= tolerance


class NumericVerifier:
    """Kiểm tra các khẳng định định lượng dựa trên bằng chứng thành công mà không dùng LLM.
        
            Với bằng chứng so sánh các kỳ, mức thay đổi được tính lại từ giá trị kỳ trước và kỳ hiện tại.
            Các dữ kiện số khác được lấy từ đầu ra Tool có cấu trúc, bao gồm các dòng metric theo nhóm.
            Chỉ kiểm tra số liệu có ngữ cảnh metric nhận diện được; văn bản đánh số thông thường được bỏ qua.
            
        """

    def verify(
        self,
        verification: VerificationReport,
        evidence: EvidenceLedger,
    ) -> NumericVerificationReport:
        evidence_by_id = {
            item.evidence_id: item
            for item in evidence.all()
            if item.execution_status is EvidenceExecutionStatus.SUCCESS
            and item.result.get("status") != "error"
        }
        findings: list[NumericFinding] = []

        for claim in verification.claims:
            mentions = _extract_mentions(claim.claim)
            if not mentions:
                continue
            cited_items = [evidence_by_id[item_id] for item_id in claim.evidence_ids if item_id in evidence_by_id]
            facts = [fact for item in cited_items for fact in _facts_for_evidence(item)]

            for mention in mentions:
                kind_candidates = [fact for fact in facts if fact.kind == mention.kind]
                candidates, matched_metric, matched_subject, binding_issue = _filter_facts_for_mention(
                    mention, kind_candidates
                )
                unique_values: list[float] = []
                source_fields: list[str] = []
                for candidate in candidates:
                    if not any(math.isclose(candidate.value, value, rel_tol=0.0, abs_tol=1e-9) for value in unique_values):
                        unique_values.append(candidate.value)
                    if candidate.source_field not in source_fields:
                        source_fields.append(candidate.source_field)

                cited_ids = list(dict.fromkeys(item.evidence_id for item in cited_items))
                if binding_issue in {"ambiguous_metric", "ambiguous_subject"}:
                    status = NumericCheckStatus.AMBIGUOUS
                    human_issue = "multiple metrics" if binding_issue == "ambiguous_metric" else "multiple subjects or periods"
                    explanation = (
                        f"Numeric value {mention.token!r} cannot be bound safely because the cited evidence contains "
                        f"{human_issue}, and the local claim does not identify which one the number refers to."
                    )
                    # Đưa các giá trị ứng viên vào báo cáo chẩn đoán, nhưng không coi chúng là giá trị khớp.
                    for fact in kind_candidates:
                        if not any(math.isclose(fact.value, value, rel_tol=0.0, abs_tol=1e-9) for value in unique_values):
                            unique_values.append(fact.value)
                        if fact.source_field not in source_fields:
                            source_fields.append(fact.source_field)
                elif binding_issue is not None:
                    status = NumericCheckStatus.NOT_CHECKABLE
                    explanation = (
                        f"Numeric value {mention.token!r} could not be matched to a comparable fact in the cited "
                        f"evidence ({binding_issue.replace('_', ' ')})."
                    )
                elif any(_mention_matches(mention, candidate) for candidate in candidates):
                    status = NumericCheckStatus.VERIFIED
                    explanation = (
                        f"Numeric value {mention.token!r} matches the cited evidence after binding the value to "
                        f"the claim's metric/subject context and applying display-rounding tolerance."
                    )
                else:
                    status = NumericCheckStatus.MISMATCH
                    pretty_expected = ", ".join(f"{value:g}" for value in unique_values)
                    explanation = (
                        f"Numeric value {mention.token!r} does not match the value(s) for the bound metric/subject "
                        f"in cited evidence: {pretty_expected}."
                    )

                findings.append(
                    NumericFinding(
                        claim_id=claim.claim_id,
                        claim=claim.claim,
                        mention=mention.token,
                        claimed_value=mention.value,
                        numeric_kind=mention.kind,
                        status=status,
                        expected_values=unique_values,
                        evidence_ids=cited_ids,
                        source_fields=source_fields,
                        matched_metric=matched_metric,
                        matched_subject=matched_subject,
                        candidate_count=len(candidates) if not binding_issue else len(kind_candidates),
                        explanation=explanation,
                    )
                )

        if not findings:
            return NumericVerificationReport(
                status=NumericVerificationStatus.NOT_APPLICABLE,
                findings=[],
                summary="No numeric metric claims required deterministic checking.",
            )

        if all(finding.status is NumericCheckStatus.VERIFIED for finding in findings):
            return NumericVerificationReport(
                status=NumericVerificationStatus.PASSED,
                findings=findings,
                summary="All detected numeric metric mentions match cited successful evidence.",
            )
        return NumericVerificationReport(
            status=NumericVerificationStatus.ISSUES_FOUND,
            findings=findings,
            summary="At least one numeric metric mention mismatches, or lacks a comparable cited fact.",
        )
