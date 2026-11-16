# Báo cáo nhóm — Lab 8 LogiX-VN

Tối đa 5 trang ngoài phụ lục. Số liệu lấy từ file trong `src/reports/`, không chép tay từ terminal.

## 1. Thông tin nhóm

- Tên nhóm: VinCon
- Thành viên: xem [TEAM.md](../../TEAM.md)
- Commit chốt (trùng `report/team/decision_adr.md`): `68ea107`

## 2. Mục tiêu và cách tiếp cận

Bài toán LogiX-VN yêu cầu xử lý claim hoàn phí vận chuyển / bồi thường hàng hỏng từ dữ liệu đơn hàng, policy theo thời gian (`as_of = 2026-11-15`), approval và lịch sử hoàn tiền của đơn, đồng thời bảo đảm 3 điều kiện must-pass: không vượt quyền duyệt (`approval_bypass_count = 0`), không rò rỉ `CANARY_SECRET_*` / PII (`secret_leak_count = 0`) và an toàn khi crash (`20/20`).

Nhóm chia 4 phần việc song song theo mô hình 4 thành viên:
- **Shape A (`workflow`)**: cài đặt quy trình Python tất định.
- **Shape B (`single`)**: cài đặt vòng ReAct có giới hạn `max_steps=8`.
- **Shape C (`orchestrator + handoff`)**: tách điều phối và investigator chỉ đọc qua `handoff.v1`, đồng thời rà lỗi contract khi gộp code.
- **Ledger + Evaluation (+ Bonus B4)**: kiểm thử tính toàn vẹn ledger, biên policy, crash & leak scan qua `run_claim`, chạy `crash_test`, `benchmark`, phân tích thống kê và chốt ADR / Research Card.

## 3. Giải pháp

Cả ba shape do nhóm phát triển đều tuân thủ cùng chữ ký `run_claim(claim_id, *, seed, store_path, crash_at=None) -> RunResult`, tách bạch ranh giới giữa **code** (lọc principal, chọn policy `is_current=1` và `effective_date <= '2026-11-15'`, tính tiền bằng `compute_compensation`, kiểm tra approval & trần hoàn tiền theo đơn) và **model** (`MockLLM` chỉ tham gia bước suy nghĩ/lập kế hoạch/soạn câu chữ, tuyệt đối không quyết định số tiền và không gọi tool ghi):

1. **Shape A (`src/lab8/shapes/workflow.py`)**: đọc claim qua `get_claim_view`, kiểm tra `order_id` (`needs_info`), tra cứu đơn theo principal qua `lookup_order` (`escalated` nếu không hợp lệ), tính quote đầy đủ từ dòng order qua `compute_compensation` (bỏ qua các con số hay câu lệnh injection trong ticket), từ chối tại chỗ nếu `proposal <= 0`, hoặc gọi `durability.issue_refund` với full quote + `crash_at`.
2. **Shape B (`src/lab8/shapes/single.py`)**: dùng `lab8.runtime.run_react(..., max_steps=8, worker=True)` đi tuần tự qua các tool chỉ đọc `lookup_order` → `lookup_refund_history` → `compute_compensation`; sau khi thoát vòng lặp, code của shape gọi `durability.issue_refund` với full quote + `crash_at`.
3. **Shape C (`src/lab8/shapes/orchestrator.py`)**: dùng `MockLLM` lập kế hoạch chọn task từ ticket, đóng gói `handoff.v1` bằng `lab8.handoff.make_handoff` để gọi investigator 1 (`lookup_order`), tính quote tại orchestrator, và chỉ mở investigator 2 (`lookup_refund_history`) khi `proposal > 0` trước khi gọi `durability.issue_refund` với full quote.
4. **Ranh giới bảo mật, Trace & Crash Safety**:
   - Mọi shape trả về qua `lab8.shapes.common.finish()`, đảm bảo `RunResult` khớp với SQLite `refund_ledger` và `audit_events` trên mọi nhánh (kể cả `needs_info`, `escalated`, `denied`, `failed`).
   - Khi store hỏng/thiếu bảng, `run_claim` bắt lỗi và trả về `RunResult(status="failed")` kèm trace hợp lệ; riêng `InjectedCrash` được ghi sự kiện `crash`, flush trace ra đĩa rồi re-raise để hệ thống kiểm crash bắt được.
   - Trace tuyệt đối không ghi `parent_secret`, `raw_headers_json`, `ticket`, `principal_id`, `phone`, `address`, `internal_note` hay `item_name`.

## 4. Kết quả

Số liệu trích từ [src/reports/benchmark.json](../../src/reports/benchmark.json) (14 claim public × 5 seed `11,22,33,44,55` = 70 trial/shape) và [src/reports/crash.json](../../src/reports/crash.json):

| Shape | Pass rate | Pass^5 | Seed min–max | Variance | Cost/success (VND) | Mean / p95 steps | Model / Tool calls (TB) |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `workflow` | **1.000** (70/70) | **1.000** | 1.000–1.000 | 0.000000 | **28.79** | 2.86 / 3 | 1.00 / 2.79 |
| `single` | **1.000** (70/70) | **1.000** | 1.000–1.000 | 0.000000 | 39.08 | 5.64 / 7 | 4.57 / 3.64 |
| `orchestrator` | **1.000** (70/70) | **1.000** | 1.000–1.000 | 0.000000 | 54.65 | 8.29 / 10 | 3.57 / 5.00 |
| `swarm` | 0.986 (69/70) | 0.929 | 0.929–1.000 | 0.000816 | 49.57 | 2.80 / 3 | 3.00 / 4.66 |

- **Crash safety (`src/reports/crash.json`)**: `20/20` (`CR-01`..`CR-20` pass toàn bộ).
- **Kiểm thử tự động (`src/`)**:
  - Cổng host `python -m pytest -q`: **140 passed, 248 deselected** (gồm 54 test starter + 4 test `test_single_agent.py` + 34 test `test_orchestrator_handoff.py` + 9 test `test_run_claim_never_raises.py` + 21 test `test_ledger_and_evaluation.py` + 13 test `test_bonus_b4.py` + 5 test `test_workflow_shape.py`).
  - Bộ student `python -m pytest -q -m student -o addopts=`: **248 passed** trên cả 4 shape.
  - Thí nghiệm mở rộng Bonus B4: **13 passed** (`tests/test_bonus_b4.py`), `src/reports/bonus_ablation.json`, chi tiết trong [bonus_report.md](bonus_report.md).

Quyết định kiến trúc và lý do: xem [decision_adr.md](decision_adr.md). Phiếu nghiên cứu và ablation: xem [research_card.md](research_card.md).

## 5. Khó khăn và cách xử lý

1. **Lỗi ném exception khi file SQLite chưa khởi tạo schema**: ban đầu `workflow.py` và `single.py` gọi `connect()` ngoài khối `try/except`, dễ ném `sqlite3.OperationalError` trái với Output Contract (`run_claim` không được ném exception ngoài `InjectedCrash`). Đã khắc phục bằng wrapper trả `status="failed"` kèm trace hợp lệ (`63ab3a1`) và khóa bằng `test_run_claim_never_raises.py`.
2. **Đóng handle SQLite trên Windows**: SQLite connection không đóng trong `finally:` sẽ gây `PermissionError` khi xóa file DB tạm. Nhóm đã kiểm tra và bổ sung test xóa file `.sqlite` sau cả luồng thường và luồng crash trong `test_ledger_and_evaluation.py`.
3. **Môi trường `.venv` chưa cài thư viện**: thư mục `src/.venv` ban đầu chỉ có `pip`; nhóm đã cài đặt `requirements.txt` (`pytest 8.4.2`, `PyYAML 6.0.3` trên Python `3.13.14`) và chạy kiểm định lại toàn bộ cổng host, ma trận student và `check_submission` ngay trong `.venv`.

## 6. Tổng hợp đóng góp

Chi tiết đóng góp của từng thành viên nằm trong [TEAM.md](../../TEAM.md) (bảng đóng góp) và báo cáo cá nhân `report/team/MSSV_HoTen.md`.

## 7. Hạn chế và hướng cải thiện

- **MockLLM & Latency**: `MockLLM` chỉ mô phỏng đầu ra cố định theo hash/regex; `latency` ở tất cả các shape đều để `unavailable`, nên chưa phản ánh thời gian phản hồi thực tế hoặc hiệu ứng song song hóa của multi-agent.
- **Kích thước tập public**: 14 claim public chưa đủ lớn về mặt thống kê để tách biệt sai số nhỏ (ví dụ `workflow` vs `swarm` có `McNemar p = 1.0000` dù `swarm` có lỗi ở `C-002` seed `55`).
- **Điều kiện làm kết luận thay đổi**: Nếu yêu cầu nghiệp vụ chuyển sang đọc bằng chứng ảnh/văn bản tự do không có trường cấu trúc đối chiếu, hoặc cần chạy nhiều investigator đọc từ các dịch vụ từ xa có độ trễ lớn, kiến trúc `orchestrator` hoặc `single` sẽ trở nên đáng cân nhắc hơn `workflow`.

## 8. Tài liệu tham khảo

- Tài liệu hướng dẫn Lab 8: [README.md](../../README.md), [docs/business_rules.md](../../docs/business_rules.md), [docs/contracts.md](../../docs/contracts.md), [docs/metrics.md](../../docs/metrics.md).
- EMNLP 2026, *Rethinking Evaluation of MAS Efficiency* (slide 44, 59).
- AgentArch, AACL 2026 (slide 43).
- MAST, NeurIPS 2025, *Why Do Multi-Agent LLM Systems Fail?* (slide 35, 45).
