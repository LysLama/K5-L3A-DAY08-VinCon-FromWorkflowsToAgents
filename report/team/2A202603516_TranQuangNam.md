# Báo cáo cá nhân — 2A202603516_TranQuangNam

## 1. Thông tin thành viên

- Họ tên: Trần Quang Nam
- MSSV: 2A202603516
- Email: 2A202603516@vinuni.edu.vn
- GitHub: TranQuangNam

## 2. Phần việc phụ trách

- Phụ trách chính **Shape B — Single ReAct Agent** (`src/lab8/shapes/single.py`).
- Xây dựng vòng lặp Bounded ReAct (`run_react`), kiểm soát công cụ đọc/ghi (Read-only vs Host write).
- Thiết kế và bổ sung bộ unit test kiểm thử chuyên biệt cho Single Agent tại `src/tests/test_single_agent.py`.
- Đảm bảo tuân thủ 3 điều kiện must-pass (không bypass approval, không rò rỉ secret/PII, bảo toàn an toàn crash 20/20).

## 3. Đóng góp cụ thể

- **Cài đặt logic ReAct cho Single Agent (`single.py`)**:
  - Tích hợp `lab8.runtime.run_react` với hàm `decide` xử lý linh hoạt 4 bước: (1) `lookup_order`, (2) `lookup_refund_history`, (3) `compute_compensation`, (4) Quyết định đề xuất hoặc từ chối.
  - Chặn cứng giới hạn bước ở `max_steps=8` và kích hoạt cờ `worker=True` để ngăn model/agent tự ý gọi công cụ ghi (`issue_refund`).
  - Phân định ranh giới rõ ràng: Dữ liệu bồi thường được trích xuất từ bảng `orders` thực tế, không tin vào các con số người dùng khai khống trong ticket (như ở T02), đồng thời kháng triệt để tấn công Prompt Injection (như ở T09).
- **Tuân thủ quy tắc Host & Idempotency**:
  - Đảm bảo shape luôn gửi **toàn bộ quote** vào cổng `durability.issue_refund`, để Host tự trừ tiền đã hoàn của đơn hàng trước đó (xử lý chính xác các trường hợp T13 và T14).
  - Tích hợp cơ chế đón và chuyển giao lỗi crash `crash_at`: bắt `InjectedCrash`, xả trace ra đĩa và re-raise để hệ thống phía trên thực hiện retry an toàn mà không bị trùng lặp tiền hoàn (đạt 20/20 crash safety).
- **Viết kiểm thử chuyên biệt (`test_single_agent.py`)**:
  - Đóng góp 4 bài unit test kiểm tra: (1) Xử lý claim giao trễ hợp lệ trong <= 8 bước, (2) Kháng prompt injection trong nội dung ticket, (3) Không để rò rỉ secret/PII trong trace log, (4) Nhận diện đúng claim thiếu `order_id` để trả về `needs_info`.

## 4. Bằng chứng

- **Mã nguồn đã thực hiện**: `src/lab8/shapes/single.py`
- **File unit test đóng góp**: `src/tests/test_single_agent.py` (4/4 tests passed)
- **Kết quả ma trận test student cho Shape B**: 62/62 tests passed trên 14 claims T01–T14 với đủ 5 seeds (`11, 22, 33, 44, 55`).
  - Lệnh kiểm tra: `python -m pytest -q -m student -o addopts= -k "single and not workflow and not orchestrator and not swarm"`
- **Cổng Host (`pytest -q`)**: 58/58 tests passed (tăng 4 tests so với starter gốc).
- **Crash Test**: Đạt 20/20 điểm (`src/reports/crash.json`).
- **Trace log**: Đáp ứng đúng chuẩn Trace contract v1, không có cảnh báo vi phạm `CANARY_SECRET_*` hay rò rỉ PII.

## 5. Công cụ AI đã dùng

- **Công cụ**: Trợ lý AI Antigravity / Gemini.
- **Mục đích sử dụng**:
  - Hỗ trợ giải thích cơ chế ReAct của runtime và cấu trúc gọi hàm `decide`.
  - Hỗ trợ xây dựng khung test `tests/test_single_agent.py`.
  - Phân tích ranh giới phân quyền bảo mật giữa Agent và Host.
- **Phương pháp tự kiểm tra**:
  - Chạy toàn bộ ma trận test student để đối chiếu kết quả từng claim với kỳ vọng thực tế (`expected`).
  - Kiểm tra các trace file sinh ra trong thư mục `traces/` để rà soát chuỗi ký tự secret (`CANARY_SECRET_*`).
  - Chạy `python -m lab8.check_submission` để đảm bảo không bị lỗi định dạng file hoặc thiếu dữ liệu.

## 6. Tự đánh giá

- Hoàn thành đầy đủ và vượt tiến độ phần việc Shape B (Single Agent).
- Mã nguồn chạy ổn định, sạch sẽ, không ném exception ngoài ý muốn, tuân thủ đúng Output Contract và Trace Contract v1.
- Điểm tự đánh giá: Hoàn thành 100% nhiệm vụ được giao.
