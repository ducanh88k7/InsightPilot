# InsightPilot — Milestone 5.5: Claim Coverage Audit

## 1. Mục tiêu

Milestone 5.4 đã liên kết con số với metric, subject và kỳ thời gian. Tuy nhiên, vẫn còn một lỗ hổng ở lớp kiểm tra ngữ nghĩa: Critic có thể trích xuất và kiểm tra một claim, nhưng bỏ quên một câu quan trọng khác trong câu trả lời nháp. Khi đó, các claim đã trích ra có thể đều `VERIFIED`, trong khi toàn bộ câu trả lời vẫn chứa nội dung chưa được kiểm tra.

Milestone 5.5 bổ sung **Claim Coverage Audit**. Bộ kiểm tra rà soát các câu hoặc mệnh đề có dấu hiệu mang thông tin phân tích trong câu trả lời, rồi xác nhận các đoạn nội dung đó đã được bao phủ bởi claim mà Critic trả về hay chưa.

Ví dụ:

```text
Revenue decreased by 35.58%.
The advertising campaign caused the decline.
```

Nếu Critic chỉ trích câu đầu thành claim, báo cáo bao phủ sẽ phát hiện câu thứ hai chưa được xem xét. Agent không được giữ quyết định `PASS` và sẽ nhận hướng dẫn sửa hoặc loại bỏ kết luận chưa được hỗ trợ.

## 2. File được thêm hoặc sửa

| File | Thay đổi |
|---|---|
| `src/insightpilot/verification/coverage.py` | File mới; tách phát biểu, xác định câu có khả năng là claim quan trọng và kiểm tra độ bao phủ. Comment/docstring mới viết bằng tiếng Việt. |
| `src/insightpilot/verification/models.py` | Thêm mô hình báo cáo bao phủ và các trạng thái `COMPLETE`, `GAPS_FOUND`, `NOT_APPLICABLE`. |
| `src/insightpilot/verification/critic.py` | Gọi auditor sau bước kiểm tra số và hạ quyết định nếu có phát biểu bị bỏ sót. |
| `src/insightpilot/verification/__init__.py` | Xuất các lớp mới khỏi package. |
| `tests/test_claim_coverage.py` | File test mới cho các trường hợp bao phủ đầy đủ, thiếu claim và tích hợp Critic. |
| `tests/test_agent.py` | Cập nhật test Fake Client cho tình huống bản tổng hợp dự phòng bị bỏ sót và phải sửa lại. |
| `README.md` | Bổ sung mô tả Milestone 5.5. |
| `pyproject.toml` | Tăng phiên bản lên `0.3.3`. |

## 3. `coverage.py` — Chi tiết các hàm

### 3.1. `_chuan_hoa_van_ban(text)`

- **Đầu vào:** Một đoạn văn bản.
- **Đầu ra:** Văn bản đã chuyển về chữ thường và khoảng trắng thống nhất; một số dấu định dạng Markdown được loại bỏ.
- **Vì sao cần:** Câu trả lời có thể dùng chữ hoa, chữ thường, xuống dòng hoặc Markdown. Chuẩn hóa giúp so khớp không bị sai chỉ vì trình bày.
- **Dùng ở đâu:** Khi so sánh đoạn claim Critic trích ra với phát biểu trong câu trả lời.

### 3.2. `_chuan_hoa_doan_trich(text)`

- **Đầu vào:** Đoạn văn bản hoặc claim.
- **Đầu ra:** Chuỗi đã chuẩn hóa, đồng thời bỏ dấu câu ở đầu và cuối.
- **Vì sao cần:** Một claim như `Revenue decreased by 35.58%` cần khớp với câu `Revenue decreased by 35.58%.` dù có khác dấu chấm kết thúc.
- **Dùng ở đâu:** Tại bước xác định claim có phải là đoạn trích nguyên văn hoặc có chứa nguyên văn phát biểu hay không.

### 3.3. `_tach_token_noi_dung(text)`

- **Đầu vào:** Văn bản đã chuẩn hóa.
- **Đầu ra:** Danh sách từ và số có ý nghĩa; các từ nối thường gặp được bỏ qua.
- **Vì sao cần:** Độ bao phủ cần tập trung vào từ mang nội dung như `revenue`, `decreased`, `35.58%`, không nên thất bại chỉ vì khác từ nối như `the`, `by` hoặc `và`.
- **Dùng ở đâu:** Tính tỉ lệ nội dung của một phát biểu đã được claim trích ra bao phủ.

### 3.4. `_tach_cac_phat_bieu(answer)`

- **Đầu vào:** Câu trả lời nháp.
- **Đầu ra:** Danh sách các câu hoặc mệnh đề được tách từ các dòng, dấu câu và một số từ nối đối lập như `while`, `but`, `trong khi`, `nhưng`.
- **Vì sao cần:** Một câu dài có thể chứa nhiều kết luận. Tách mệnh đề giúp phát hiện trường hợp câu đầu được kiểm tra nhưng câu sau bị bỏ qua.
- **Giới hạn:** Đây là bộ tách dựa trên quy tắc văn bản, không phải parser ngôn ngữ đầy đủ. Các câu có dấu câu bất thường, dấu chấm trong chữ viết tắt hoặc bảng Markdown phức tạp có thể được tách chưa hoàn hảo.

### 3.5. `_la_phat_bieu_can_kiem_tra(statement)`

- **Đầu vào:** Một câu hoặc mệnh đề.
- **Đầu ra:** `True` nếu phát biểu có số liệu hoặc chứa từ khóa thường gắn với phân tích; ngược lại là `False`.
- **Vì sao cần:** Các câu chào hỏi hoặc câu dẫn nhập không cần trở thành claim dữ liệu. Bộ lọc từ khóa giúp tập trung vào số liệu, metric, xu hướng, thứ hạng và quan hệ nhân quả.
- **Dùng ở đâu:** Trước khi đưa phát biểu vào báo cáo bao phủ.

Bộ từ khóa có cả tiếng Anh và một số cụm tiếng Việt như `doanh thu`, `lợi nhuận`, `số lượng`, `trung bình`, `dữ liệu`, `sản phẩm`, `thay đổi`, `nguyên nhân` và `quảng cáo`.

### 3.6. `_chi_so_bao_phu(statement_tokens, claim_tokens)`

- **Đầu vào:** Token quan trọng của một phát biểu và token thu được từ claim liên quan.
- **Đầu ra:** Tỉ lệ bao phủ từ `0.0` đến `1.0` cùng danh sách token còn thiếu.
- **Vì sao cần:** Cho biết phát biểu đã được trích xuất đầy đủ hay mới chỉ có một phần nội dung được đưa vào báo cáo.
- **Quy tắc:** Trong phiên bản này, tỉ lệ `1.0` mới được coi là bao phủ đầy đủ.

### 3.7. `ClaimCoverageAuditor.audit(draft_answer, verification)`

Đây là hàm công khai của module.

**Đầu vào:**

- `draft_answer`: toàn bộ câu trả lời nháp được tạo bởi Agent.
- `verification`: báo cáo chứa các claim mà Critic đã tách ra và xác minh.

**Đầu ra:** Một `ClaimCoverageReport` gồm trạng thái chung, tổng số phát biểu, số phát biểu đã bao phủ, danh sách `ClaimCoverageFinding` và phần tóm tắt.

Quy trình:

1. Tách câu trả lời thành các câu hoặc mệnh đề.
2. Lọc ra các phát biểu có dấu hiệu mang thông tin phân tích.
3. Chuẩn hóa văn bản của mỗi claim và đối chiếu bằng quan hệ đoạn trích nguyên văn.
4. Tính phần nội dung được bao phủ và giữ lại từ khóa chưa được bao phủ để debug.
5. Trả về `COMPLETE`, `GAPS_FOUND` hoặc `NOT_APPLICABLE`.

## 4. Các mô hình báo cáo mới trong `models.py`

### `ClaimSegmentStatus`

- `COVERED`: nội dung quan trọng của phát biểu đã được claim trích xuất bao phủ.
- `UNCOVERED`: chưa tìm thấy claim phù hợp hoặc còn thiếu token nội dung.

### `ClaimCoverageStatus`

- `COMPLETE`: mọi phát biểu được bộ lọc nhận diện đều đã được bao phủ.
- `GAPS_FOUND`: còn phát biểu chưa được bao phủ.
- `NOT_APPLICABLE`: không phát hiện câu nào cần kiểm tra theo bộ lọc hiện tại.

### `ClaimCoverageFinding`

| Trường | Ý nghĩa |
|---|---|
| `segment_id` | Mã phát biểu, ví dụ `S001`. |
| `statement` | Văn bản phát biểu đang được kiểm tra. |
| `status` | `COVERED` hoặc `UNCOVERED`. |
| `matched_claim_ids` | Các claim được ghép với phát biểu. |
| `coverage_ratio` | Tỉ lệ nội dung được bao phủ. |
| `uncovered_tokens` | Các từ hoặc số còn thiếu. |
| `explanation` | Lý do tạo ra finding. |

### `ClaimCoverageReport`

- `status`: trạng thái tổng thể.
- `statement_count`: số phát biểu được bộ lọc chọn kiểm tra.
- `covered_count`: số phát biểu đã bao phủ.
- `findings`: kết quả của từng phát biểu.
- `summary`: tóm tắt dễ đọc.
- `to_dict()`: chuyển toàn bộ báo cáo sang kiểu dữ liệu thuận tiện cho `AgentResult`, log và JSON.

`VerificationReport` được bổ sung `claim_coverage_report`, vì vậy báo cáo mới xuất hiện cùng `numeric_report` khi gọi `to_dict()`.

## 5. Tích hợp vào `critic.py`

Sau khi Critic trả về JSON, luồng hiện tại vẫn thực hiện kiểm tra ID bằng chứng và NumericVerifier. Sau đó, bước mới gọi:

```python
coverage_report = self.claim_coverage_auditor.audit(draft_answer, verification)
verification.claim_coverage_report = coverage_report
self._apply_coverage_findings(verification, critic, coverage_report)
```

### `_apply_coverage_findings(...)`

- **Đầu vào:** `VerificationReport`, `CriticReport` và `ClaimCoverageReport`.
- **Đầu ra:** Cập nhật báo cáo và quyết định hiện có; không tạo request LLM.
- **Vì sao cần:** Kết quả kiểm tra bao phủ phải có ảnh hưởng đến quyết định cuối, chứ không chỉ lưu để xem.

Khi tìm được gap:

1. Nếu báo cáo trước đó là `VERIFIED`, chuyển thành `PARTIALLY_VERIFIED`.
2. Thêm `CriticIssue` loại `claim_coverage_gap` để giữ câu bị bỏ sót.
3. Nếu Critic đang `PASS`, hạ xuống `NEEDS_REVISION`.
4. Thêm chỉ dẫn sửa: bổ sung claim với bằng chứng phù hợp, hoặc loại bỏ/diễn đạt thận trọng phát biểu chưa được hỗ trợ.

Bước này không tự khẳng định phát biểu bị bỏ sót là sai. Nó chỉ xác nhận rằng phát biểu ấy chưa được đánh giá đầy đủ, nên không thể coi toàn bộ câu trả lời đã qua kiểm tra.

## 6. Kiểm thử

File `tests/test_claim_coverage.py` thêm các bài test:

- Phát hiện câu giải thích nguyên nhân bị bỏ ngoài danh sách claim.
- Xác nhận hai mệnh đề đều được bao phủ nếu có đủ hai claim.
- Bỏ qua tiêu đề và câu dẫn nhập thông thường.
- Hạ `PASS` khi còn phát biểu quan trọng bị bỏ sót.
- Serialize báo cáo và giữ lại token chưa bao phủ.
- Trả `NOT_APPLICABLE` nếu không có phát biểu phân tích phù hợp.

Test `synthesis_failure` trong `tests/test_agent.py` được cập nhật: nếu bản tóm tắt dự phòng có nội dung mà review đầu tiên bỏ sót, Agent được phép sửa một lần rồi review lại; các Tool phân tích không bị chạy lại.

Kết quả kiểm thử trong môi trường triển khai: **83 passed**. Ba demo offline cũng chạy thành công:

```bash
PYTHONPATH=src python run_demo.py
PYTHONPATH=src python run_tools_demo.py
PYTHONPATH=src python run_planning_demo.py
```

Các test và demo này không gọi LLM API thật.

## 7. Giới hạn cần biết

1. Coverage audit dùng bộ tách câu và từ khóa heuristic. Nó có thể bỏ sót claim diễn đạt bằng từ nằm ngoài từ điển hoặc gắn cờ quá mức với định dạng đặc biệt.
2. `COMPLETE` có nghĩa là các phát biểu mà bộ lọc nhận diện đã được bao phủ, không phải bằng chứng toán học rằng mọi câu trong câu trả lời đều đúng.
3. Coverage audit chỉ kiểm tra tính đầy đủ của việc trích xuất claim. Việc xác định claim có được bằng chứng hỗ trợ hay không vẫn do xác minh evidence ID, Critic và NumericVerifier đảm nhiệm.
4. Critic được yêu cầu trích claim như một đoạn nguyên văn của draft để giảm khả năng ghép nhầm với một câu khác.

## 8. Khởi tạo Git từ mốc 5.5

Theo quyết định của người dùng, không đẩy Milestone 5.4 riêng. Sau khi áp dụng toàn bộ thay đổi Milestone 5.5 và chạy test ở máy cá nhân, khởi tạo Git tại thư mục gốc có `pyproject.toml`:

```bash
git init
git branch -M main
git status --short
git add .
git diff --cached --stat
git commit -m "feat: add claim coverage audit for milestone 5.5"
```

Sau đó tạo repository GitHub rỗng tên `InsightPilot` rồi kết nối và đẩy:

```bash
git remote add origin https://github.com/<USERNAME>/InsightPilot.git
git push -u origin main
git tag -a milestone-5.5 -m "InsightPilot Milestone 5.5"
git push origin milestone-5.5
```

Thay `<USERNAME>` bằng username GitHub của bạn. Trước khi chạy `git add .`, kiểm tra `.gitignore` và chắc chắn không có `.env`, API key hoặc dữ liệu riêng tư bị đưa vào commit.
