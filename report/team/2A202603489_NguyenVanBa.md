# Báo cáo cá nhân — 2A202603489_NguyenVanBa

## 1. Thông tin thành viên

- Họ tên: Nguyễn Văn Ba
- MSSV: 2A202603489
- Email: nguyenvanba.tinhoc@gmail.com
- GitHub: xtraiter

## 2. Phần việc phụ trách

- **Shape C — orchestrator và investigator chỉ đọc** (`src/lab8/shapes/orchestrator.py`).
- **Ranh giới handoff:** dữ kiện chuyển cho investigator chỉ đi qua `lab8.handoff.make_handoff`, trace chỉ ghi handoff đã sanitize.
- **Test cho shape C** (`src/tests/test_orchestrator_handoff.py`).
- **Gộp code ba shape** và sửa một lỗi contract chung khi gộp (xem mục 3).

Shape A (workflow) và shape B (single) do hai thành viên khác viết; tôi giữ nguyên logic của họ, chỉ sửa đúng một lỗi contract ở hàm `run_claim` của hai file đó. Benchmark 4 shape, ADR và báo cáo nhóm thuộc phần việc của thành viên khác.

## 3. Đóng góp cụ thể

### Luồng của orchestrator

1. Đọc claim bằng `get_claim_view` (không đọc dòng thô vì có `parent_secret`). Một lời gọi model lập kế hoạch từ ticket; kế hoạch chỉ chọn việc cần làm, không chọn số tiền.
2. Thiếu `order_id` → `needs_info`, không gọi investigator.
3. Handoff `verify_order_facts` → investigator chỉ có tool `lookup_order`. Không thấy đơn hoặc sai principal → `escalated`.
4. Orchestrator tự tính quote bằng `compute_compensation` từ order view investigator trả về. Quote = 0 → `denied`, không gọi host.
5. Chỉ khi quote > 0: handoff `check_prior_refunds` → investigator thứ hai chỉ có tool `lookup_refund_history`, nhận các dữ kiện của đơn qua allowlist.
6. Orchestrator gọi `durability.issue_refund` với **quote đầy đủ** và `crash_at`. Host từ chối → `denied` (giữ nguyên quote, host ghi audit `policy_denied`); conflict → `failed`; còn lại → `resolved`.

### Quyết định kỹ thuật

- **Truyền quote đầy đủ, không tự trừ.** Investigator thứ hai báo đơn đã được hoàn bao nhiêu, nhưng con số đó chỉ để soạn câu trả lời và ghi trace. Host tự đọc lại tổng đã hoàn trong chính transaction ghi, nên nếu shape trừ trước thì bị trừ hai lần (T14 sẽ ra 90.000 thay vì 120.000).
- **Investigator thứ hai có điều kiện.** Claim không có gì để hoàn thì không tốn thêm một lần handoff; đây là chỗ orchestrator khác với một workflow cố định.
- **Handoff fail-closed.** Nếu dữ kiện chứa secret, `make_handoff` ném `HandoffError`; shape trả `failed`, không ghi ledger, trace chỉ ghi tên loại lỗi.
- **`run_claim` không ném exception** ngoài `InjectedCrash`. Mọi lỗi khác (kể cả không mở được file store) trả `failed` kèm trace hợp lệ. `InjectedCrash` được ghi trace rồi ném lại để T12 thấy crash thật.
- **Trace cố ý không ghi:** nội dung ticket, `principal_id`, `parent_secret`, header, dòng claim/order thô, thông báo lỗi của exception. Chỉ ghi handoff đã sanitize, kết quả tool đã qua allowlist, quote và lý do host trả về.
- **Cùng quy ước chi phí với nhóm.** Prompt của lời gọi draft giống workflow, single và swarm để phần chi phí draft bằng nhau giữa các shape.

### Sửa lỗi contract ở workflow và single

`docs/contracts.md` yêu cầu `run_claim` không được ném exception. Bản gốc của `workflow.py` và `single.py` mở store ngoài mọi khối xử lý lỗi, nên store không mở được hoặc không có bảng thì ném `sqlite3.OperationalError`. Tôi bọc `run_claim` của hai file để trả `failed` kèm trace hợp lệ; `InjectedCrash` vẫn được ném ra như cũ. Phần `_run` của hai bạn không đổi, và kết quả benchmark của cả bốn shape giống hệt trước khi sửa.

### Commit và test

- Commit chính:
  - `63053c5` — `feat(orchestrator)`: shape C và test của nó.
  - `63ab3a1` — `fix(workflow,single)`: không ném exception khi store không dùng được.
- Test đã thêm: `src/tests/test_run_claim_never_raises.py`, 9 test trên cả ba shape: store không mở được, store không có bảng, và `InjectedCrash` vẫn lọt ra ngoài.
- Test đã thêm: `src/tests/test_orchestrator_handoff.py`, 34 test:
  - 10 ca đối kháng tự gắn nhãn tay theo `docs/business_rules.md`, chạy ở seed 11 và 55: ticket nói quá số ngày trễ, approval mượn của claim khác, approval bị thu hồi, đơn hủy, đơn đang giao, mã đơn homoglyph, ship + hỏng hàng cùng đủ điều kiện, hỏng hàng chưa verify, trần theo `paid_vnd`, principal khác chủ đơn.
  - Quote = 0 không tạo audit nào (host không bị gọi).
  - Host từ chối thì `proposal_amount` vẫn là quote đầy đủ và có đúng một audit `policy_denied`.
  - Crash ở cả ba điểm rồi resume: đúng một dòng ledger, một audit `refund_committed`.
  - Handoff chỉ chứa field, fact key và tool trong allowlist; secret trong facts làm run dừng mà không trả tiền.
  - Claim không tồn tại: trả `failed`, không ném exception.

## 4. Bằng chứng

Chạy trong `src/`, trên code đã gộp với workflow và single của nhóm:

| Lệnh | Kết quả |
| --- | --- |
| `python -m pytest -q tests/test_orchestrator_handoff.py` | 34 passed |
| `python -m pytest -q tests/test_run_claim_never_raises.py` | 9 passed |
| `python -m pytest -q -m student -o addopts= -k orchestrator` | 62 passed |
| `python -m pytest -q` (cổng host) | 101 passed |
| `python -m pytest -q -m student -o addopts=` (4 shape) | 248 passed |
| `python -m lab8.crash_test --count 20 --out reports/crash.json` | `crash_safety 20/20` |

Shape C trên bộ public, 14 claim × 5 seed (`11,22,33,44,55`), lấy từ lệnh benchmark trong `src/reports/README.md`:

| Metric | Giá trị |
| --- | --- |
| Pass rate | 1.000 (70/70) |
| Pass^5 | 1.000 |
| Seed min–max / variance | 1.000–1.000 / 0 |
| Cost per success (mô phỏng) | 54.65 VND |
| Mean / p95 steps | 8.29 / 10 |
| Mean model calls / tool calls | 3.57 / 5.0 |

- Run id minh họa: `R-orchestrator-C-014-s11` (T14: proposal 150.000, ledger 120.000, trace có hai handoff).
- File `src/reports/benchmark.json` chính thức do thành viên phụ trách phần đánh giá sinh ra; số của shape C ở trên chỉ phụ thuộc `orchestrator.py` nên chạy lại phải khớp.
- Các lệnh trên chạy bằng Python 3.11.

## 5. Công cụ AI đã dùng

- **Công cụ:** Claude Code (Anthropic).
- **Dùng vào việc gì:** đọc đề và code host; viết `orchestrator.py` và hai file test; gộp code của nhóm và sửa lỗi contract ở `workflow.py`, `single.py`; soạn bản nháp báo cáo này.
- **Cách kiểm tra kết quả:**
  - Chạy các lệnh ở mục 4 trên máy cá nhân, đối chiếu từng claim public với nhãn `expected`.
  - Nhãn của 10 ca đối kháng viết tay từ luật nghiệp vụ, không sinh bằng `compensation.quote`.
  - Đọc trace của T14 và T05 để chắc không có ticket, secret, SĐT, địa chỉ hay ghi chú nội bộ.
- Không dùng AI để tạo số liệu: mọi con số ở mục 4 là output của công cụ lab.

## 6. Tự đánh giá

...
