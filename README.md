# InsightPilot — Milestone 5.5: Kiểm tra độ bao phủ khẳng định

InsightPilot là dự án AI Data Analyst. Dự án giữ lại Data Analysis Engine (Milestone 1), Tool Layer (Milestone 2), Single Agent (Milestone 3), các cải tiến nhận biết dữ liệu và phục hồi lỗi (Milestone 3.5), cùng tích hợp Planner/Executor (Milestone 4).

## Kiến trúc

```text
Người dùng
 ↓
DataAnalystAgent.ask()
 ↓
Preflight / Hồ sơ dataset
 ↓
Router
 ├── Direct → Vòng lặp LLM ↔ ToolRegistry
 └── Planned → Planner → AnalysisPlan → Executor → ToolRegistry
                                                    ↓
                                              AnalysisContext
                                                    ↓
                                         Ghi nhận kết quả Tool
                                                    ↓
                                         Tổng hợp cuối (không Tool)
 ↓
AgentResult: câu trả lời + chỉ số request/tool/step/thời gian
```

## Chạy test và demo offline

```bash
python -m pip install -e .
pytest -q
python run_planning_demo.py
```

Test và demo lập kế hoạch xác định không gọi API LLM thật.

## Chạy demo Agent thật

Demo trực tiếp cần `OPENAI_API_KEY` hợp lệ và model ID khả dụng trong `OPENAI_MODEL`. Các lần gọi OpenAI API có thể phát sinh chi phí.

## Milestone 5.2 — Bằng chứng và xác minh của Critic

Agent ghi đầu ra Tool vào `EvidenceLedger` riêng cho từng câu hỏi, bao gồm preflight, Direct Mode và Planned Mode. `CriticVerifier` đối chiếu câu trả lời nháp với bằng chứng thành công, từ chối ID bằng chứng không tồn tại hoặc đến từ Tool thất bại, và có thể yêu cầu viết lại một lần trước khi trả lời. Các lượt review/sửa không thực thi Tool phân tích.

`AgentResult` có thêm `evidence_ledger`, `verification_report`, `critic_report` và `review_attempts`. Các lần gọi Critic và sửa câu trả lời được tính vào `llm_requests` và có thể phát sinh chi phí khi chạy thật. Test dùng Fake Client và demo offline không gọi API LLM thật.

Xem [`MILESTONE5_2.md`](MILESTONE5_2.md) để biết kiến trúc, hợp đồng dữ liệu, phạm vi và chi tiết kiểm thử.

## Milestone 5.3 — Xác minh số học xác định

`NumericVerifier` kiểm tra số liệu theo bằng chứng thành công được viện dẫn. Với so sánh theo kỳ, chương trình tính lại mức thay đổi tuyệt đối và phần trăm từ `previous` và `current`, kiểm tra hướng diễn đạt tăng/giảm, rồi ghi các kết quả `VERIFIED`, `MISMATCH` hoặc `NOT_CHECKABLE` vào `VerificationReport.numeric_report`. Sai lệch số học có thể hạ quyết định Critic từ `PASS` xuống `NEEDS_REVISION`. Các phép kiểm tra này chạy cục bộ, không gọi thêm LLM.

Xem [`MILESTONE5_3.md`](MILESTONE5_3.md) để biết giải thích code theo từng file, hợp đồng dữ liệu, ví dụ tính toán và giới hạn.

## Milestone 5.4 — Gắn khẳng định với đúng bằng chứng

Milestone 5.4 khiến việc xác minh số học thận trọng hơn. Các dữ kiện số giữ lại tên metric và, với dữ liệu theo nhóm hoặc chuỗi thời gian, nhãn sản phẩm/chiều phân loại hoặc kỳ tương ứng. Một con số phải khớp với metric và đối tượng được nêu trong mệnh đề; không được thông qua chỉ vì cùng giá trị xuất hiện ở metric hoặc dòng sản phẩm không liên quan. Nếu còn nhiều metric/đối tượng có thể phù hợp, kết quả là `AMBIGUOUS` và Critic không được giữ `PASS` khi chưa giải quyết được sự mơ hồ.

Các test bao gồm: không gán doanh thu Laptop cho Keyboard; không dùng phần trăm thay đổi của profit để xác minh revenue; gắn giá trị với đúng tháng; phân biệt số hàng và số cột; đánh dấu mơ hồ khi có nhiều nguồn có thể khớp.

Bộ quét số cũng giới hạn việc phân loại trong mệnh đề cục bộ và hỗ trợ cách viết số thập phân bằng dấu phẩy. Nếu câu khẳng định nêu metric hoặc sản phẩm không xuất hiện trong bằng chứng được viện dẫn, hệ thống không xác minh nó chỉ vì giá trị duy nhất sẵn có tình cờ khớp.

Xem [`MILESTONE5_4.md`](MILESTONE5_4.md) để đọc giải thích chi tiết, đầu vào/đầu ra, quy tắc ghép và giới hạn. Bản này đã vượt qua 76 test và ba demo offline.

## Milestone 5.5 — Kiểm tra độ bao phủ khẳng định

Milestone 5.5 bổ sung bước rà soát độ bao phủ cục bộ sau khi đã kiểm tra ngữ nghĩa và số học. `ClaimCoverageAuditor` quét câu trả lời nháp để tìm các phát biểu phân tích có ý nghĩa (dựa trên mẫu số và một bộ từ khóa tiếng Anh/tiếng Việt), sau đó kiểm tra xem mỗi phát biểu có được đại diện trong danh sách claim mà Critic trích xuất hay không. Báo cáo được lưu vào `VerificationReport.claim_coverage_report`. Nếu một phát biểu quan trọng bị bỏ sót, Critic không được giữ `PASS`; hệ thống thêm vấn đề `claim_coverage_gap` và hướng dẫn sửa câu trả lời.

Bộ rà soát là heuristic thận trọng, không phải bộ trích xuất phát biểu ngôn ngữ tự nhiên hoàn chỉnh. Nó có thể bỏ sót claim nằm ngoài từ khóa hoặc nhận diện nhầm khi văn bản có định dạng bất thường. Critic được hướng dẫn trích nguyên văn claim từ câu trả lời nháp và chương trình đối chiếu đoạn văn bản để hạn chế khớp nhầm. Việc xác minh số học và kiểm tra ID bằng chứng vẫn là các bước độc lập.

Xem [`MILESTONE5_5.md`](MILESTONE5_5.md) để đọc hợp đồng đầu vào/đầu ra, giải thích code, test, giới hạn và hướng dẫn khởi tạo Git. Test dùng client giả, không gọi API LLM thật.
