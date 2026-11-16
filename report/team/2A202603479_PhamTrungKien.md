# Báo cáo cá nhân — 2A202603479_PhamTrungKien

## 1. Thông tin thành viên

- Họ tên: Phạm Trung Kiên
- MSSV: 2A202603479
- Email: trungkienpham0607@gmail.com
- GitHub: kienpham0607

## 2. Phần việc phụ trách

- Phụ trách chính **Shape A — deterministic workflow** (`src/lab8/shapes/workflow.py`).
- Viết pipeline cố định: đọc claim → tra đơn theo quyền → tính quote từ order DB → gọi host ghi refund khi cần.
- Đảm bảo ranh giới **code quyết tiền / MockLLM chỉ soạn chữ**; truyền **quote đầy đủ** và `crash_at` vào `durability.issue_refund`.
- Tài liệu giải thích nội bộ: `docs/huong_dan_workflow.md` (không nằm trong repo nộp).
- Shape B (single) và shape C (orchestrator), benchmark/ADR/báo cáo nhóm do thành viên khác phụ trách.

## 3. Đóng góp cụ thể

### Luồng workflow đã cài

1. Mở store bằng `connect(store_path)`, luôn `close` trong `finally`.
2. Đọc claim qua `get_claim_view` (không `SELECT *` để tránh lộ `parent_secret`).
3. Claim không tồn tại → `failed`; thiếu `order_id` → `needs_info`, không ghi ledger; không lấy mã đơn từ chữ trong ticket.
4. `lookup_order` theo `principal_id`. Không visible → `escalated` (không trả phone, địa chỉ, tên hàng, internal note).
5. Quote bằng `compute_compensation` từ **dòng order**, bỏ qua số ngày trễ / câu lệnh trong ticket.
6. Quote ≤ 0 → `denied`, **không** gọi `issue_refund`.
7. Quote > 0 → `issue_refund(conn, claim_id, proposal, crash_at=crash_at)` với **full quote**. Host ok → `resolved`; host chặn → `denied` (giữ `proposal_amount` = quote); conflict → `failed`.
8. Bắt `InjectedCrash`: ghi event crash vào trace, `trace.write()`, rồi **re-raise** (không nuốt exception) để T12 thấy crash thật.
9. Mọi nhánh trả kết quả qua `lab8.shapes.common.finish()` và `lab8.trace.Trace` đúng Trace contract v1.

### Quyết định kỹ thuật

- **Tiền nằm ở code, không ở model.** MockLLM chỉ gọi `complete(..., purpose="draft")` để soạn chữ / ghi budget; không dùng output model để chọn số tiền hay commit refund.
- **Truyền quote đầy đủ, không tự trừ.** Host tự trừ phần đơn đã được hoàn bởi claim khác trong transaction ghi. Tự trừ trước sẽ bị trừ hai lần (T14 sai).
- **Tin order DB, không tin ticket.** Tránh weakness kiểu swarm (tin delay trong ticket ở một số seed).
- **Trace tối giản, fail-closed về bảo mật.** Chỉ ghi `found` / `has_order_id`, kết quả lookup (visible/reason), quote payload, điểm crash — không dump ticket, claim row hay order row thô.
- **Cùng quy ước chi phí với nhóm.** Có `budget.add_tool(tool_cost())` mỗi lần gọi tool đọc và một lần draft, để so sánh cost giữa các shape công bằng.

### Commit và test

- `1d00761` — `feat : done workflow`: thay stub `not_implemented` bằng shape A đầy đủ (CP2 + CP3 trong cùng file).
- Sau đó thành viên phụ trách orchestrator đã bọc thêm `run_claim` ở commit `63ab3a1` để store hỏng trả `failed` thay vì ném exception (đúng `docs/contracts.md`); phần logic `_run` của workflow giữ nguyên ý đồ trên.
- Test đã thêm: `src/tests/test_workflow_shape.py` — resolve T01, không tin ticket (T02), không lộ secret/PII, `needs_info` khi thiếu `order_id`, T13 giữ full quote khi host từ chối.

## 4. Bằng chứng

Chạy trong thư mục `src/`:

| Lệnh | Kết quả |
| --- | --- |
| `python -m lab8.smoke` | `lab8.smoke pass` |
| `python -m pytest -q tests/test_workflow_shape.py` | **5 passed** |
| `python -m pytest -q -m student -o addopts= -k workflow` | **62 passed** (T01–T14 × seed, gồm T11/T12) |
| `python -m pytest -q` (cổng host) | xanh trên máy làm bài |
| `python -m lab8.run --shape workflow --claim-id C-001 --seed 11 --db data/run.sqlite` | claim T01 chạy được |

- Mã nguồn: `src/lab8/shapes/workflow.py`
- Test đóng góp: `src/tests/test_workflow_shape.py`
- Commit shape: [`1d00761`](https://github.com/LysLama/K5-Day8-VinCon-From-Workflows-to-Agents/commit/1d00761)
- Dòng đóng góp trong `TEAM.md`: Phạm Trung Kiên · Workflow + integration · `1d00761` · `test_workflow_shape.py`
- Run id minh họa: `R-workflow-C-001-s11` (T01 hoàn ship theo quote từ order).
- Case đối chiếu tay:
  - **T02:** ticket phóng đại delay → workflow vẫn theo DB → không trả nhầm như weakness của swarm.
  - **T13:** đơn đã hoàn đủ → `denied`, `proposal_amount` vẫn là full quote, host ghi `policy_denied`.
  - **T14:** truyền full quote → host chỉ ghi phần chênh; `proposal_amount` không bị shape tự trừ.

## 5. Công cụ AI đã dùng

- **Công cụ:** Cursor (agent hỗ trợ code).
- **Dùng vào việc gì:**
  - Đọc đề (`CHECKPOINTS.md`, `docs/business_rules.md`, `docs/contracts.md`) và mẫu `swarm_reference.py`.
  - Viết / hoàn thiện `workflow.py` theo docstring CP2–CP3.
  - Soạn `docs/huong_dan_workflow.md` (không nằm trong repo nộp) và bản nháp báo cáo cá nhân này.
- **Cách tự kiểm tra kết quả:**
  - Chạy smoke + `pytest -m student -k workflow` trên máy cá nhân, đối chiếu status/proposal với luật nghiệp vụ.
  - Không dùng AI để bịa số liệu benchmark, run id hay commit.
  - Tự giải thích được: vì sao tiền do `compute_compensation`, vì sao full quote, vì sao không bắt chết `InjectedCrash`, field nào cố ý không ghi vào trace.

## 6. Tự đánh giá

- **Mức hoàn thành:** Hoàn thành phần việc Shape A (workflow + integration) đúng phạm vi được giao. Shape chạy đủ nhánh contract (`needs_info` / `escalated` / `denied` / `resolved` / `failed`), ma trận student workflow **62/62** xanh, có truyền `crash_at` và trace không lộ secret/PII.
- **Điểm làm tốt:** Giữ ranh giới rõ — tiền chỉ do `compute_compensation`, refund chỉ qua host, tin order DB chứ không tin ticket; truyền full quote nên T13/T14 đúng; cấu trúc `run_claim` / `_run` / `finish` dễ đọc và đồng bộ với các shape khác trong nhóm.
- **Đã học được:** Hiểu vì sao checkpoint đơn lẻ không thay được ledger; vì sao shape không được tự trừ phần đã hoàn; vì sao trace là ranh giới bảo mật chứ không phải log debug; workflow ít tự chủ nhưng thường ổn định hơn swarm khi so cùng seed.
- **Hạn chế / cải thiện:** Ban đầu dễ nhầm vì bám `swarm_reference` quá sát (cần chủ động bỏ weakness tin ticket). Đã bổ sung `test_workflow_shape.py` và dòng đóng góp trong `TEAM.md`. Nếu làm lại, sẽ viết unit test hẹp ngay từ CP2 song song với shape.
- **Tự chấm phần việc cá nhân:** Đạt mục tiêu kỹ thuật của vai workflow; sẵn sàng giải thích trực tiếp luồng shape A, full quote, `InjectedCrash` và field cố ý không ghi vào trace.
