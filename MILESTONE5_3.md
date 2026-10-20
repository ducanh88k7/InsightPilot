# InsightPilot — Milestone 5.3: Deterministic Numeric Verification

## 1. Mục tiêu

Milestone 5.2 đã yêu cầu LLM xác định các khẳng định trong câu trả lời, sau đó code kiểm tra ID bằng chứng và trạng thái thực thi của Tool. Tuy nhiên, LLM vẫn có thể gọi một con số sai là `VERIFIED` nếu nó diễn giải nhầm kết quả.

Milestone 5.3 bổ sung một lớp kiểm tra số học bằng Python. Với kết quả so sánh kỳ có `previous` và `current`, verifier tự tính lại:

- `absolute_change = current - previous`
- `percentage_change = (current - previous) / previous * 100`, nếu `previous != 0`

Ví dụ, khi doanh thu kỳ trước là 26.000 và kỳ hiện tại là 16.750:

- Thay đổi tuyệt đối = `16.750 - 26.000 = -9.250`.
- Thay đổi phần trăm = `-9.250 / 26.000 × 100 = -35,5769...%`.
- Câu “Doanh thu giảm 35,58%” được chấp nhận theo dung sai làm tròn.
- Câu “Doanh thu giảm 30%” bị đánh dấu `MISMATCH`, kể cả khi LLM đã tự gắn nhãn `VERIFIED`.
- Câu “Doanh thu tăng 35,58%” bị đánh dấu sai hướng vì bằng chứng tính toán có dấu âm.

Đây không thay thế Critic ngữ nghĩa. LLM vẫn nhận diện các khẳng định và bằng chứng phù hợp; NumericVerifier kiểm tra những giá trị số được nhận diện bằng các quy tắc xác định, không gọi API LLM.

## 2. Files được thêm hoặc sửa

### File code mới

- `src/insightpilot/verification/numeric.py` — trích xuất khẳng định định lượng, tạo các fact số từ kết quả Tool và kiểm tra số liệu.
- `tests/test_numeric_verification.py` — unit test cho phép tính phần trăm, thay đổi tuyệt đối, giá trị trong bảng nhóm, giá trị sai, sai chiều tăng/giảm và tích hợp Critic.

### Files code được sửa

- `src/insightpilot/verification/models.py` — thêm enum và dataclass cho báo cáo numeric; `VerificationReport` chứa trường `numeric_report`.
- `src/insightpilot/verification/critic.py` — sau khi xác minh ID bằng chứng, gọi NumericVerifier và áp dụng phát hiện số học vào báo cáo.
- `src/insightpilot/verification/__init__.py` — export các lớp public mới.
- `tests/test_agent.py` — chỉnh Fake Critic ở kịch bản fallback dài để mô phỏng việc LLM tách khẳng định quan trọng, thay vì xem toàn bộ JSON log là một khẳng định duy nhất.
- `pyproject.toml` — tăng phiên bản lên `0.3.1` và cập nhật mô tả dự án.
- `README.md` — bổ sung mô tả và cách chạy Milestone 5.3.

`src/insightpilot/agent/core.py` không cần sửa ở milestone này: Core đã gọi `CriticVerifier.review()` và đưa `VerificationReport.to_dict()` vào `AgentResult`. Numeric report mới được gắn vào VerificationReport nên tự xuất hiện trong kết quả trả về của Agent.

## 3. `numeric.py` — chi tiết các hàm

### 3.1. Các regex và cấu trúc nội bộ

`_ISO_DATE_RE` che những ngày ISO như `2026-10-20` trước khi quét số, để ngày tháng không bị hiểu nhầm là số liệu phân tích.

`_NUMBER_RE` tìm các số phổ biến như `35.58%`, `9,250`, `26,000` và `35,58%`. Đây là bản đầu tiên, chủ ý ưu tiên cách viết số thông thường thay vì hỗ trợ mọi định dạng tự do.

`_METRIC_WORD_RE`, `_PERCENT_CONTEXT_RE`, `_CHANGE_CONTEXT_RE`, `_DOWN_CONTEXT_RE`, `_UP_CONTEXT_RE` và `_COUNT_CONTEXT_RE` giúp phân loại số theo ngữ cảnh. Chúng phân biệt phần trăm, thay đổi tuyệt đối, giá trị metric và số đếm. Ví dụ, `35.58%` trong câu về doanh thu là phần trăm; `9,250` trong “decreased by 9,250” là mức thay đổi tuyệt đối; `34,800` trong “Laptop revenue was 34,800” là giá trị metric.

`_NumericMention` lưu một con số được tìm thấy trong lời khẳng định: token gốc, giá trị đã parse, loại số, ngữ cảnh, việc có dấu `+/-` tường minh hay không và số chữ số thập phân dùng để ước lượng dung sai làm tròn.

`_NumericFact` lưu một giá trị số từ bằng chứng: giá trị, loại fact, ID bằng chứng và đường dẫn trường nguồn.

### 3.2. `_parse_number(token: str) -> float`

**Đầu vào:** một token số được tìm bằng regex, ví dụ `35.58%`, `9,250` hoặc `35,58%`.

**Xử lý:** bỏ ký hiệu `%`/từ `percent`; xử lý dấu phẩy/dấu chấm theo cách viết số phổ biến; chuyển thành `float`.

**Đầu ra:** số Python, ví dụ `35.58` hoặc `9250.0`.

**Tại sao cần:** so sánh số yêu cầu giá trị số chứ không phải chuỗi văn bản. Hàm giữ được giá trị số trong khi dấu `%` và dấu phân tách hàng nghìn không làm sai phép so sánh.

### 3.3. `_number_kind(claim, start, end, token) -> str | None`

**Đầu vào:** toàn bộ câu khẳng định, vị trí của token số và chính token đó.

**Xử lý:** nhìn vào một cửa sổ văn bản quanh con số để phân loại nó. Các loại hiện hỗ trợ gồm:

- `percentage_change`: số có `%` hoặc ngữ cảnh phần trăm.
- `absolute_change`: số được diễn đạt như mức tăng/giảm/thay đổi.
- `count`: số hàng, bản ghi, cột hoặc số lượng.
- `metric_value`: một giá trị metric, ví dụ doanh thu của Laptop.
- `None`: không có dấu hiệu cho thấy đây là khẳng định số liệu cần kiểm tra.

**Đầu ra:** tên loại hoặc `None`.

**Tại sao cần:** không nên dùng số đếm hàng trong dataset để xác minh một khẳng định về phần trăm doanh thu. Phân loại làm giảm nguy cơ ghép nhầm những số không cùng ý nghĩa.

### 3.4. `_extract_mentions(claim: str) -> list[_NumericMention]`

**Đầu vào:** văn bản của một `ClaimVerification.claim` do Critic tạo ra.

**Xử lý:** che ngày ISO, tìm token số, parse token, xác định loại và số chữ số thập phân, rồi chỉ giữ số có ngữ cảnh metric phù hợp.

**Đầu ra:** danh sách các `_NumericMention` cần kiểm tra. Câu “Laptop là sản phẩm có doanh thu cao nhất” không tạo ra numeric mention. Câu “Doanh thu giảm 35,58%” tạo ra một mention loại `percentage_change`.

**Tại sao cần:** NumericVerifier kiểm tra từng khẳng định mà Critic đã nhận diện, không quét mù mọi con số trong prompt hoặc trong toàn bộ lịch sử hội thoại.

### 3.5. `_finite_number(value: object) -> float | None`

**Đầu vào:** một giá trị từ kết quả Tool.

**Xử lý:** chỉ chấp nhận `int`/`float` hữu hạn; loại `bool`, chuỗi, NaN và vô cực.

**Đầu ra:** số hữu hạn hoặc `None`.

**Tại sao cần:** các giá trị không phải số và số không hữu hạn không được dùng làm fact định lượng.

### 3.6. `_fact_kind(path: str) -> str`

**Đầu vào:** đường dẫn của trường trong kết quả Tool, ví dụ `result.percentage_change`, `result.row_count` hoặc `result.rows[0].revenue`.

**Xử lý:** phân loại trường theo tên.

**Đầu ra:** `percentage_change`, `absolute_change`, `count` hoặc `metric_value`.

**Tại sao cần:** NumericVerifier cần so số với một fact cùng loại. Phần trăm được so với phần trăm; thay đổi tuyệt đối được so với thay đổi tuyệt đối; doanh thu trong các hàng của `group_metric` được xem là metric value.

### 3.7. `_iter_numeric_leaves(value, path='result')`

**Đầu vào:** một kết quả Tool dạng dictionary/list có thể lồng nhau.

**Xử lý:** đi đệ quy qua dictionary/list; khi gặp một giá trị số hữu hạn, trả về cặp `(path, number)`.

**Đầu ra:** iterator của các đường dẫn trường và số tương ứng.

**Tại sao cần:** kết quả `group_metric` có thể chứa các hàng như `rows[0].revenue`, còn profile có thể chứa số hàng/số cột. Không thể chỉ đọc các trường cấp cao nhất.

### 3.8. `_facts_for_evidence(item: EvidenceItem) -> list[_NumericFact]`

**Đầu vào:** một bằng chứng từ EvidenceLedger.

**Xử lý:** bỏ bằng chứng lỗi; sau đó lấy các số trong kết quả. Với kết quả so sánh có cả `previous` và `current`, hàm **tính lại** thay đổi tuyệt đối và phần trăm từ hai đầu mút. Các trường `absolute_change` và `percentage_change` đã có trong kết quả bị bỏ qua khi tạo fact so sánh, để tránh tin mù quáng vào chính những trường cần được xác minh.

**Đầu ra:** các fact được gắn loại và nguồn.

**Tại sao cần:** đây là bước trung tâm tạo nguồn sự thật định lượng. Ví dụ, ngay cả khi kết quả Tool chứa `percentage_change: -999`, các fact để xác minh vẫn dùng `previous=26000` và `current=16750`, nên phần trăm kỳ vọng được tính thành khoảng `-35.5769%`.

Nếu `previous == 0`, phần trăm không được tạo vì phép chia đó không xác định; một khẳng định phần trăm khi ấy sẽ không được xác minh bằng quy tắc này.

### 3.9. `_rounding_tolerance(mention)`

**Đầu vào:** numeric mention cùng số chữ số thập phân hiển thị.

**Xử lý:** tạo dung sai bằng nửa đơn vị ở chữ số cuối cùng hiển thị, với dung sai tối thiểu rất nhỏ cho sai số floating-point.

**Ví dụ:** `35.58%` được hiển thị đến hai chữ số thập phân nên có thể khớp với giá trị tính toán `35.576923...%`; `30%` thì không thể khớp với giá trị đó.

**Tại sao cần:** so sánh float bằng dấu bằng tuyệt đối dễ bác bỏ một con số được làm tròn chính xác.

### 3.10. `_direction_matches(mention, expected)`

**Đầu vào:** mention và giá trị kỳ vọng có dấu.

**Xử lý:** nếu ngữ cảnh diễn đạt giảm, giá trị kỳ vọng phải âm; nếu ngữ cảnh diễn đạt tăng, giá trị kỳ vọng phải dương. Câu không biểu thị hướng sẽ không bị ép hướng bằng từ ngữ.

**Đầu ra:** `True` nếu hướng được diễn đạt tương thích với dấu của giá trị.

**Tại sao cần:** “tăng 35,58%” và “giảm 35,58%” có cùng độ lớn nhưng là hai kết luận trái ngược. Chỉ so sánh trị tuyệt đối sẽ không phát hiện được lỗi này.

### 3.11. `_mention_matches(mention, fact)`

**Đầu vào:** số được nêu trong khẳng định và một fact đã phân loại.

**Xử lý:** so sánh theo dung sai; với mức thay đổi, còn kiểm tra hướng tăng/giảm. Nếu câu ghi rõ dấu âm/dương, dấu cũng được so sánh.

**Đầu ra:** Boolean cho biết mention có khớp fact hay không.

**Tại sao cần:** gom logic so khớp vào một hàm duy nhất để các đơn vị kiểm tra cùng tuân theo một quy tắc.

### 3.12. `NumericVerifier.verify(verification, evidence)`

**Đầu vào:**

- `verification`: `VerificationReport` do Critic ngữ nghĩa tạo ra, chứa những khẳng định và ID bằng chứng đã được kiểm tra sơ bộ.
- `evidence`: EvidenceLedger của lượt hỏi hiện tại.

**Xử lý:**

1. Tạo bảng tra cứu chỉ gồm bằng chứng thành công và không có `status='error'`.
2. Đọc các ID bằng chứng của mỗi khẳng định; chỉ lấy fact từ đúng những bằng chứng được trích dẫn.
3. Trích xuất numeric mention trong câu khẳng định.
4. Tìm các fact cùng loại.
5. Gán `VERIFIED` nếu có fact khớp; `MISMATCH` nếu có fact cùng loại nhưng giá trị/hướng không khớp; `NOT_CHECKABLE` nếu không có fact so sánh phù hợp.
6. Tổng hợp thành `NumericVerificationReport`.

**Đầu ra:** báo cáo số học có trạng thái tổng thể, các finding, giá trị kỳ vọng và nguồn bằng chứng.

**Tại sao cần:** hàm này chạy hoàn toàn bằng Python, không gọi LLM. Nó cung cấp một kiểm tra độc lập đối với phần số liệu mà Critic đã nhận diện.

## 4. `models.py` — Các kiểu dữ liệu báo cáo mới

### `NumericCheckStatus`

- `VERIFIED`: số khớp với fact được kiểm tra.
- `MISMATCH`: có fact cùng loại nhưng số hoặc hướng không khớp.
- `NOT_CHECKABLE`: bằng chứng được trích dẫn không có fact thích hợp để xác minh số đó.

### `NumericVerificationStatus`

- `PASSED`: tất cả numeric finding đều được xác minh.
- `ISSUES_FOUND`: có ít nhất một số sai hoặc chưa thể kiểm tra.
- `NOT_APPLICABLE`: không tìm thấy numeric metric claim nào cần kiểm tra.

### `NumericFinding`

Các trường quan trọng:

- `claim_id`, `claim`: khẳng định nào đang được kiểm tra.
- `mention`, `claimed_value`, `numeric_kind`: token và cách phân loại số trong câu.
- `status`: kết quả của lần kiểm tra.
- `expected_values`: giá trị tìm thấy/tính lại từ bằng chứng.
- `evidence_ids`, `source_fields`: nguồn và đường dẫn trường đã đối chiếu.
- `explanation`: diễn giải vì sao số được chấp nhận hoặc bị báo lỗi.

### `NumericVerificationReport`

Chứa trạng thái tổng thể, danh sách `NumericFinding` và phần tóm tắt. Phương thức `to_dict()` chuẩn hóa enum thành chuỗi để kết quả dùng được trong `AgentResult`, log và test.

### Trường mới `VerificationReport.numeric_report`

`VerificationReport` đã chứa các kết quả kiểm tra khẳng định từ Critic; trường mới này đính kèm kết quả số học bên trong báo cáo đó. Nhờ vậy, `DataAnalystAgent` vốn đã serialize `VerificationReport.to_dict()` không cần thêm một nhánh lưu trữ riêng.

## 5. Thay đổi trong `critic.py`

### `CriticVerifier.__init__()`

Khởi tạo `self.numeric_verifier = NumericVerifier()`. NumericVerifier không có client LLM vì nó chỉ tính toán và so khớp bằng Python.

### Thay đổi trong `review()`

Sau khi LLM trả báo cáo và `_validated_reports()` kiểm tra ID bằng chứng, luồng mới chạy tiếp:

```python
verification, critic = self._validated_reports(payload, evidence)
numeric_report = self.numeric_verifier.verify(verification, evidence)
verification.numeric_report = numeric_report
self._apply_numeric_findings(verification, critic, numeric_report)
return verification, critic
```

Dòng thứ nhất là phần review ngữ nghĩa ở Milestone 5.2. Dòng thứ hai là bước kiểm tra số độc lập. Dòng thứ ba lưu báo cáo số vào báo cáo xác minh tổng. Dòng thứ tư áp dụng các lỗi số liệu trở lại kết quả tổng hợp.

### `_apply_numeric_findings(verification, critic, numeric_report)`

Hàm này áp dụng phát hiện số học vào các báo cáo đã tạo:

- Nếu một số `MISMATCH`, khẳng định tương ứng chuyển thành `CONTRADICTED` và thêm `CriticIssue` loại `numeric_mismatch` mức `HIGH`.
- Nếu `NOT_CHECKABLE` mà LLM đã đánh dấu `VERIFIED`, khẳng định chuyển thành `NOT_VERIFIABLE`, thêm `numeric_not_checkable` mức `MEDIUM`.
- Tính lại `VerificationStatus` tổng thể dựa trên các trạng thái khẳng định mới.
- Nếu Critic đã chọn `PASS` nhưng NumericVerifier phát hiện lỗi/chưa kiểm tra được, quyết định bị hạ xuống `NEEDS_REVISION`.
- Thêm hướng dẫn sửa để loại bỏ hoặc sửa khẳng định số liệu không khớp.

Đây là hàng rào quan trọng: LLM không thể giữ một khẳng định được đánh dấu `VERIFIED` và một quyết định `PASS` khi phép kiểm tra số xác định có mâu thuẫn.

## 6. Luồng chạy sau Milestone 5.3

```text
Tool Results
   ↓
EvidenceLedger
   ↓
LLM Critic: tách khẳng định + đánh giá ngữ nghĩa
   ↓
Kiểm tra ID và trạng thái bằng chứng bằng code
   ↓
NumericVerifier: parse số + tính lại + so khớp
   ↓
Gộp kết quả vào VerificationReport / CriticReport
   ├── PASS → trả lời
   └── NEEDS_REVISION → sửa tối đa một lần → review lại
```

`DataAnalystAgent` tiếp tục điều phối và vẫn sửa tối đa một lần. Revision và review đều không cung cấp các Tool phân tích, do đó không thực thi lại các phép phân tích.

## 7. Giới hạn có chủ đích

- Bộ parse hiện tập trung vào số được viết trực tiếp, ví dụ `35.58%`, `9,250` hoặc `34,800`. Cách viết rút gọn như `35.6K`, số viết bằng chữ và mọi định dạng đơn vị phức tạp chưa được bảo đảm.
- Loại số được xác định từ ngữ cảnh ngắn và các từ khóa định lượng. Các câu dài, mơ hồ hoặc có nhiều metric cùng lúc có thể cần rule mở rộng.
- Verifier hiện kiểm tra các khẳng định mà Critic đã trích xuất và chỉ dùng ID evidence của khẳng định đó. Nếu Critic bỏ sót một khẳng định số liệu, bước số học không thể tự phát hiện khẳng định đó.
- Với kết quả so sánh, giá trị thay đổi được tính lại từ `previous` và `current`. Với các kết quả Tool khác, số được đọc từ cấu trúc kết quả, chưa tự tái dựng toàn bộ phép aggregation từ DataFrame nguồn.
- `VERIFIED` ở lớp số học chỉ có nghĩa các con số được hỗ trợ bởi phép tính hoặc trường kết quả phù hợp; nó không chứng minh mọi diễn giải ngữ nghĩa của câu là đúng.

## 8. Test được thêm

`tests/test_numeric_verification.py` kiểm tra:

1. Phần trăm chính xác được tính từ `previous/current`, ngay cả khi `percentage_change` lưu trong Tool result sai.
2. Phần trăm sai bị phát hiện.
3. Hướng tăng/giảm sai bị phát hiện dù độ lớn phần trăm khớp.
4. Các hướng tăng/giảm khác nhau trong cùng một câu được đối chiếu theo từng mệnh đề.
5. Phần trăm âm không được chấp nhận chỉ vì câu nêu đúng trị tuyệt đối nhưng bỏ hướng/dấu.
6. Thay đổi tuyệt đối chính xác/sai được kiểm tra từ đầu mút.
7. Numeric facts trong hàng của `group_metric` được xác minh.
8. Thiếu fact cùng loại trở thành `NOT_CHECKABLE`.
9. Claim không có số liệu không sinh numeric finding.
10. Critic bị hạ từ `PASS` khi con số mâu thuẫn với phép tính xác định.
11. Numeric report được serialize bên trong VerificationReport.

## 9. Chạy dự án

Tại thư mục gốc:

```bash
python -m pip install -e .
pytest -q
python run_demo.py
python run_tools_demo.py
python run_planning_demo.py
```

Test và demo offline dùng Fake Client/dữ liệu mẫu, không cần gọi LLM API. Live Agent vẫn cần `OPENAI_API_KEY` và một model ID khả dụng trong `OPENAI_MODEL`; các request live có thể phát sinh chi phí.
