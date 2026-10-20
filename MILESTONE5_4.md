# InsightPilot — Milestone 5.4: Claim-to-Evidence Binding

## 1. Mục tiêu

Milestone 5.3 đã tính lại các con số và so sánh chúng với bằng chứng được trích dẫn. Nhưng cách so khớp cũ còn một lỗ hổng: nó có thể chấp nhận một con số nếu **bất kỳ** fact nào cùng loại khớp, dù fact đó thuộc một metric, sản phẩm hoặc kỳ thời gian khác.

Ví dụ, evidence có:

- Revenue giảm 35,58%.
- Profit tăng 20%.

Nếu câu trả lời viết “Revenue decreased by 20%” và viện dẫn cả hai bản ghi, cách any-match cũ có thể lấy 20% từ profit để chấp nhận câu nói về revenue.

Milestone 5.4 thêm binding theo ngữ cảnh: **số → loại số → metric → subject/dimension/period → bằng chứng đã trích dẫn**. Nếu evidence đưa ra nhiều khả năng và câu không nêu đủ ngữ cảnh để chọn, hệ thống đánh dấu `AMBIGUOUS`, không đoán.

## 2. Các file được thêm hoặc sửa

### File code được sửa

- `src/insightpilot/verification/numeric.py`: gắn tên metric, subject và trường nguồn vào NumericFact; tách từng câu/mệnh đề; ràng buộc số với metric hoặc subject đã nêu; phân biệt trường hợp mơ hồ.
- `src/insightpilot/verification/models.py`: thêm `NumericCheckStatus.AMBIGUOUS` và các trường chẩn đoán trong `NumericFinding`.
- `src/insightpilot/verification/critic.py`: xử lý kết quả mơ hồ như trường hợp chưa thể xác minh; tự động hạ `PASS` xuống `NEEDS_REVISION`.
- `tests/test_numeric_verification.py`: thêm test ngăn khớp nhầm metric, sản phẩm, tháng, số hàng/cột và các trường hợp có nhiều candidate.
- `README.md`: ghi nhận khả năng mới.
- `pyproject.toml`: tăng phiên bản từ `0.3.1` lên `0.3.2`.

Không thêm file runtime mới trong milestone này. `numeric.py` và `CriticVerifier` hiện có được gia cố; đây tiếp tục là một bước nâng cấp của NumericVerifier.

## 3. File `numeric.py` — chi tiết phần được bổ sung

### 3.1. Mở rộng `_NumericFact`

```python
@dataclass(frozen=True)
class _NumericFact:
    value: float
    kind: str
    evidence_id: str
    source_field: str
    metric_name: str | None = None
    subject: str | None = None
    subject_field: str | None = None
```

- `value`: số được lấy hoặc tính từ Tool result.
- `kind`: ví dụ `percentage_change`, `absolute_change`, `metric_value`, `count`.
- `evidence_id`: bằng chứng nguồn.
- `source_field`: trường nguồn như `rows[0].revenue` hoặc công thức tính.
- `metric_name`: metric được phân tích, ví dụ `revenue` hay `profit`.
- `subject`: hàng, sản phẩm hay kỳ mà số thuộc về.
- `subject_field`: trường đã dùng làm subject, ví dụ `product` hoặc `date`.

**Tại sao cần bổ sung các trường này?** Số `20%` tự nó không đủ để xác minh câu nào đúng. Ta phải biết nó là phần trăm thay đổi của metric nào và có thuộc đúng đối tượng/kỳ mà câu nói đến không.

### 3.2. `_clause_for_span(claim, start, end)`

**Đầu vào:** câu khẳng định cùng vị trí bắt đầu/kết thúc của một numeric mention.

**Đầu ra:** phần mệnh đề chứa con số đó.

Hàm cắt mệnh đề theo dấu câu và từ nối phổ biến như `while`, `whereas`, `but`, `and`. Ví dụ:

```text
Revenue decreased by 35.58%, while profit increased by 20%.
```

Số `35.58%` được kiểm tra với mệnh đề về revenue; số `20%` được kiểm tra với mệnh đề về profit. Điều này giảm nguy cơ lấy metric từ một phần câu bên cạnh.

`_extract_mentions()` nay dùng mệnh đề cục bộ này làm `context` của `_NumericMention`, để bước binding áp dụng đúng phạm vi.

### 3.3. `_result_column(item, key)`

**Đầu vào:** một `EvidenceItem` và tên metadata như `metric_col`, `dimension_col` hoặc `date_col`.

**Đầu ra:** giá trị chuỗi lấy từ Tool result; nếu không có thì dùng arguments lúc gọi Tool; nếu cả hai không có thì trả `None`.

**Tại sao cần?** Các Tool trả metadata trực tiếp trong result, nhưng metadata cũng có thể chỉ tồn tại trong arguments. Cần một nơi thống nhất để tìm tên cột metric/subject.

### 3.4. `_normalise_label(label)` và `_label_in_text(label, text)`

`_normalise_label()` chuyển chữ về dạng không phân biệt hoa thường, thay dấu gạch dưới/gạch ngang bằng khoảng trắng và chuẩn hóa khoảng trắng.

`_label_in_text()` kiểm tra một cụm từ hoàn chỉnh sau chuẩn hóa, thay vì dùng tìm kiếm substring tùy tiện. Nó được dùng để nhận diện subject như `Laptop`, `Keyboard`, tên tháng hoặc nhãn kỳ.

**Tại sao không chỉ dùng `if label in text`?** Nếu tìm chuỗi con không có ranh giới, một nhãn ngắn có thể khớp nhầm với nhãn khác dài hơn.

### 3.5. `_metric_match_quality(metric, text)`

Hàm trả về:

- `2` nếu tên metric xuất hiện chính xác.
- `1` nếu chỉ khớp qua alias có kiểm soát, ví dụ `row_count` với “rows”, hoặc `total_revenue` được gọi rút gọn là “revenue”.
- `None` nếu không có dấu hiệu khớp.

**Đầu vào:** tên trường metric từ Tool evidence và mệnh đề quanh con số.

**Đầu ra:** mức độ khớp cho biết metric có được nêu trong câu hay không.

Nếu có nhiều trường metric chỉ khớp thông qua một hậu tố chung — ví dụ `gross_profit` và `net_profit`, trong khi câu chỉ nói “profit” — hàm binding không tự chọn một trường. Nó trả về trạng thái mơ hồ.

### 3.6. `_subject_for_path(item, path)`

**Đầu vào:** một `EvidenceItem` và đường dẫn số như `result.rows[0].revenue`.

**Đầu ra:** `(subject, subject_field)`, ví dụ `("Laptop", "product")` hoặc `(date_value, "date")`.

Hàm lấy đúng hàng trong list `rows`, ưu tiên trường `dimension_col`, tiếp đó là `date_col`. Nếu metadata không có, chỉ dùng fallback khi hàng có một nhãn chuỗi không phải metric duy nhất; nếu có nhiều khả năng thì không đoán.

**Áp dụng:** `group_metric` để ràng buộc số với sản phẩm/nhóm; `period_metric` để ràng buộc số với kỳ thời gian.

### 3.7. `_facts_for_evidence(item)` đã được mở rộng

Hàm này trước đây chỉ tạo các fact số theo loại và nguồn. Nay nó giữ thêm metric, subject và source field.

Với tool so sánh hai kỳ:

- `previous` trở thành `metric_value` của `previous period`.
- `current` trở thành `metric_value` của `current period`.
- `absolute_change` vẫn được tính lại bằng `current - previous`.
- `percentage_change` vẫn được tính lại bằng `(current - previous) / previous * 100`, nếu `previous != 0`.

Các nhãn kỳ đặc biệt giúp câu “Current revenue was 16,750” có thể ràng buộc vào `current`; câu “August revenue was 16,750” thì không được suy ra từ comparison result nếu bản ghi không lưu tên tháng. Khi period metric có các hàng ngày tháng thật, `_subject_for_path()` lấy ngày từ mỗi hàng để có thể đối chiếu tên tháng.

### 3.8. `_subject_aliases(subject)`

**Đầu vào:** nhãn subject trong evidence.

**Đầu ra:** tập các tên gọi được chấp nhận có căn cứ.

Ví dụ ngày ISO `2026-08-01T00:00:00` có thể tạo các alias `August`, `Aug` và `tháng 8`. Các nhãn `previous period` và `current period` cũng nhận alias hạn chế như `previous`/`prior` và `current`/`latest`.

Không thêm alias tùy tiện cho mọi nhãn, vì alias không được kiểm soát có thể khiến nhiều đối tượng khác nhau bị nhập làm một.

### 3.9. `_filter_facts_for_mention(mention, candidates)`

Đây là hàm binding chính. Nó nhận một numeric mention cùng những fact có cùng loại, rồi trả về:

```text
(candidates_after_binding, matched_metric, matched_subject, binding_issue)
```

Quy trình:

1. Xác định metric name xuất hiện trong mệnh đề.
2. Nếu một metric khớp rõ ràng, chỉ giữ fact của metric ấy.
3. Nếu nhiều metric vẫn có khả năng nhưng không thể phân biệt, trả `ambiguous_metric`.
4. Tìm subject/period được nêu trong mệnh đề.
5. Nếu match một subject, loại bỏ các fact thuộc subject khác.
6. Nếu còn nhiều subject mà câu không chỉ ra đối tượng nào, trả `ambiguous_subject`.
7. Nếu tên metric hoặc subject không tồn tại trong phần evidence có thể sử dụng, trả lý do chưa thể kiểm tra.

**Tại sao cần hàm này?** Đây là phần ngăn hành vi “chỉ cần một số giống là đủ”. Chỉ những fact phù hợp với metric/subject trong chính mệnh đề mới được dùng để xác minh.

### 3.10. Thay đổi trong `NumericVerifier.verify()`

Trước đây, logic kiểm tra là: lấy mọi fact cùng `kind`, rồi đánh dấu `VERIFIED` nếu bất kỳ fact nào khớp. Nay logic được thay bằng:

1. Lấy fact cùng loại.
2. Gọi `_filter_facts_for_mention()` để bind chúng theo metric/subject.
3. Chỉ so sánh giá trị trên tập fact đã bind.
4. Ghi các trường chẩn đoán `matched_metric`, `matched_subject`, `candidate_count` vào `NumericFinding`.

Kết quả:

- **`VERIFIED`**: số khớp với fact thuộc đúng metric/subject.
- **`MISMATCH`**: metric/subject đã xác định được, nhưng số không đúng.
- **`NOT_CHECKABLE`**: không có fact cùng loại hoặc bằng chứng không cung cấp dữ liệu cần thiết.
- **`AMBIGUOUS`**: có nhiều metric/subject có thể phù hợp và câu không nêu đủ thông tin để chọn.

Ví dụ: `Keyboard revenue was 34,800` sẽ bị đánh dấu sai nếu bằng chứng cho thấy Laptop là 34.800 còn Keyboard là 4.200. Câu `Revenue was 4,200` khi bằng chứng chỉ chứa nhiều sản phẩm nhưng không nói đến sản phẩm nào sẽ là `AMBIGUOUS`, thay vì được chấp nhận do một dòng bất kỳ có giá trị 4.200.

## 4. `models.py` — các trường báo cáo mới

### `NumericCheckStatus.AMBIGUOUS`

Trạng thái mới dùng khi có các candidate cùng loại số nhưng không thể ràng buộc duy nhất vào metric/subject theo mệnh đề. Nó khác `MISMATCH`: hệ thống không khẳng định số sai, mà nói rằng chưa xác định được số cần so với fact nào.

### Các trường thêm vào `NumericFinding`

- `matched_metric`: metric mà verifier đã xác định, nếu có.
- `matched_subject`: sản phẩm/nhóm/kỳ mà verifier đã xác định, nếu có.
- `candidate_count`: số candidate được so sánh hoặc xem xét.

Các trường này nhằm tăng khả năng giải thích và debug. `to_dict()` serialize chúng để có thể xem trực tiếp trong `AgentResult.verification_report.numeric_report`.

## 5. `critic.py` — xử lý ambiguity

`CriticVerifier._apply_numeric_findings()` nay xem `AMBIGUOUS` cùng nhóm với `NOT_CHECKABLE`:

- Nếu LLM đánh dấu claim `VERIFIED` nhưng con số vẫn ambiguous, claim được hạ xuống `NOT_VERIFIABLE`.
- Một `CriticIssue` loại `numeric_ambiguous` được thêm vào báo cáo.
- Nếu quyết định ban đầu là `PASS`, nó bị hạ thành `NEEDS_REVISION`.
- Hướng dẫn sửa khuyên Agent nêu rõ metric/subject hoặc bỏ số chưa thể xác minh.

Không có lần gọi LLM bổ sung chỉ để binding; logic này chạy cục bộ. Nếu Agent cần viết lại thì luồng revision có sẵn từ Milestone 5.2 sẽ xử lý nó theo giới hạn một lần đã đặt ra.

## 6. Test mới

`tests/test_numeric_verification.py` bao gồm các tình huống mới:

1. Giá trị đúng của Laptop được xác minh, nhưng gán cùng giá trị cho Keyboard bị bác bỏ.
2. Không lấy phần trăm của profit để hỗ trợ phát biểu về revenue.
3. Câu không nêu metric khi evidence chứa revenue và profit bị đánh dấu `AMBIGUOUS`.
4. Không mượn metric duy nhất đang có (revenue) để xác minh câu tuyên bố profit.
5. Không gán giá trị của Laptop cho Keyboard, kể cả khi evidence chỉ có một hàng nhưng claim nêu một subject không xuất hiện.
6. Giá trị tháng 8 được ghép với đúng hàng tháng 8, không ghép với tháng 7.
7. Số hàng không bị nhầm với số cột.
8. Critic không được giữ `PASS` khi numeric binding còn mơ hồ.
9. Các trường `gross_profit` và `net_profit` không bị nhập làm một khi câu chỉ nói “profit”; khi câu nói rõ “gross profit”, verifier có thể chọn đúng metric.
10. Giá trị thuộc comparison result yêu cầu ngữ cảnh previous/current nếu cả hai đầu mút đều là candidate.
11. Nhãn metric tiếng Việt như “doanh thu” có thể bind tới cột `revenue`, và số trong một mệnh đề không mượn ngữ cảnh đếm từ mệnh đề kế tiếp.

## 7. Chạy kiểm thử và demo

Từ thư mục gốc:

```bash
python -m pip install -e .
pytest -q
python run_demo.py
python run_tools_demo.py
python run_planning_demo.py
```

Kiểm tra đóng gói Milestone 5.4 sử dụng `PYTHONPATH=src` và không gọi API LLM thật. Bản này có 76 test trong bộ kiểm thử dự án.

## 8. Phạm vi và giới hạn

- Việc trích xuất numeric mention vẫn dựa trên regex và cách viết số phổ biến, gồm dấu phẩy/dấu chấm thập phân và hàng nghìn; không bao quát mọi cách viết tự do như `35.6K`, khoảng số hay phép tính viết bằng lời.
- Binding theo metric/subject là quy tắc bảo thủ, dựa trên tên trường, label hàng và ngữ cảnh mệnh đề. Tên cột quá khác cách diễn đạt trong câu có thể khiến giá trị thành `NOT_CHECKABLE` thay vì tự động suy đoán.
- Với comparison result chỉ có `previous`/`current` mà không có nhãn tháng, verifier không tự gán tháng cho hai endpoint.
- Các khẳng định phi số như quan hệ nhân quả vẫn cần Critic ngữ nghĩa và các bước xác minh khác.

Milestone 5.4 thu hẹp đáng kể lỗi “số đúng nhưng gắn nhầm đối tượng”. Nó làm NumericVerifier thận trọng hơn: khi không chứng minh được số thuộc đúng metric, sản phẩm hoặc kỳ, hệ thống sẽ yêu cầu làm rõ thay vì đoán.
