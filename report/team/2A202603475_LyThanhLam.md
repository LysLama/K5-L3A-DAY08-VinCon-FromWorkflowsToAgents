# Báo cáo cá nhân — 2A202603475_LyThanhLam

## 1. Thông tin thành viên

- Họ tên: Lý Thanh Lâm
- MSSV: 2A202603475
- Email: thanhlam211204@gmail.com
- GitHub: lyslama

## 2. Phần việc phụ trách

- Phụ trách mảng **Ledger + Evaluation** cho nhóm **VIncon** (nhánh 4 người):
  - Kiểm định ranh giới `durability.issue_refund`, `policy.authorize`, trần hoàn tiền theo đơn (`cap_per_order`), idempotency, conflict, bảo mật trace khi crash, và vệ sinh đóng handle SQLite trên Windows.
  - Chạy toàn bộ quy trình đánh giá định lượng (`lab8.crash_test`, `lab8.benchmark`, `lab8.check_submission`).
  - Phụ trách hoàn thiện **ADR** ([decision_adr.md](decision_adr.md)), **Research Card** ([research_card.md](research_card.md)) và tổng hợp phần Kết quả / Hạn chế trong **Group Report** ([group_report.md](group_report.md)).
  - Thực hiện phần **Bonus B4 — Baseline công bằng, ablation và thống kê** (`src/bonus/`, `src/tests/test_bonus_b4.py`, [bonus_report.md](bonus_report.md)).

## 3. Đóng góp cụ thể

- **Bộ test chuyên sâu cho Ledger, Policy, Crash & Evaluation (`src/tests/test_ledger_and_evaluation.py`)**:
  - 21 test mới chạy trong cổng host mặc định (`pytest -q`), không sửa bất kỳ file host/thước đo bị khóa nào (`metrics.py`, `durability.py`, `policy.py`, `config/`, `data/`).
  - Kiểm chứng toàn diện 3 shape của nhóm (`workflow`, `single`, `orchestrator`) qua 3 điểm crash (`before_effect`, `after_effect_before_checkpoint`, `after_checkpoint`), rà soát không rò `CANARY_SECRET_*` và PII ngay tại thời điểm crash, kiểm tra `cap_per_order` khi chạy nhiều claim liên tiếp qua `run_claim` (`C-001` → `C-010`, `C-014`), kiểm tra `amount_conflict`, biên ngày hết hạn approval (`2026-11-15` vs `2026-11-14`), trần `paid_vnd - already_refunded_vnd`, vệ sinh đóng file `.sqlite` trên Windows, và các kiểm tra toàn vẹn của `metrics.summarize` / `trial_pass` / `run_benchmark`.
- **Chạy kiểm định & sinh bằng chứng chính thức (`src/reports/`)**:
  - Chạy `lab8.crash_test` (`20/20`) tại `src/reports/crash.json`.
  - Chạy `lab8.benchmark` (4 shape × 14 claims × 5 seeds = 280 trials) tại `src/reports/benchmark.json`, xác nhận `workflow`, `single`, `orchestrator` đạt `1.000 / 1.000` (`variance = 0`), `swarm` đạt `0.986 / 0.929` (`variance = 0.000816`).
- **Bonus B4 — Baseline công bằng, ablation & thống kê chuẩn (`src/bonus/`)**:
  - `src/bonus/stats.py`: cài đặt bằng thư viện chuẩn Python (`math`, `random`, `collections`) hàm `bootstrap_pass_rate_ci` (cluster bootstrap resample theo `claim_id`), `paired_mcnemar` (exact two-sided binomial qua `math.comb`) và `paired_sign_test`.
  - `src/bonus/b4_shapes.py`: cài đặt 2 baseline (`rules_only` 0 model calls, `swarm_pruned` cắt ngẫu nhiên `peer`/`parse` theo seed) và 2 ablation (`workflow_trust_ticket`, `orchestrator_no_history_inv`) giữ nguyên chữ ký `run_claim` và tương thích `--extra-shape`.
  - `src/bonus/run_b4.py` & `src/tests/test_bonus_b4.py`: sinh `src/reports/bonus_ablation.json`, `src/reports/bonus_benchmark.json` và 13 unit test kiểm định các biến thể và công thức thống kê.

## 4. Bằng chứng

- Commit kỹ thuật chính: `68ea107`
- File mã nguồn & test đóng góp:
  - `src/tests/test_ledger_and_evaluation.py` (**21 passed**)
  - `src/bonus/__init__.py`, `src/bonus/stats.py`, `src/bonus/b4_shapes.py`, `src/bonus/run_b4.py`
  - `src/tests/test_bonus_b4.py` (**13 passed**)
- File báo cáo & dữ liệu chạy lại được:
  - `src/reports/crash.json` (`crash_safety 20/20`)
  - `src/reports/benchmark.json` (4 shape × 14 claims × 5 seeds: `workflow` pass `1.000`, cost/success `28.79 VND`)
  - `src/reports/bonus_ablation.json` & `src/reports/bonus_benchmark.json`
  - `report/team/decision_adr.md`, `report/team/research_card.md`, `report/team/group_report.md`, `report/team/bonus_report.md`, `TEAM.md`
- Lệnh đã chạy và kết quả (trong `src/` với `.venv` Python `3.13.14`):
  - `python -m pytest -q` → **135 passed, 248 deselected** (gồm cả 21 test ledger/eval và 13 test bonus B4)
  - `python -m pytest -q -m student -o addopts=` → **248 passed, 135 deselected**
  - `python -m lab8.check_submission` → **0 FAIL, 0 WARN**

## 5. Công cụ AI đã dùng

- **Công cụ**: Trợ lý AI Antigravity (Google Deepmind / Gemini).
- **Dùng vào việc gì**:
  - Đọc và rà soát toàn bộ mã nguồn host (`durability.py`, `policy.py`, `metrics.py`, `benchmark.py`, `check_submission.py`) và kiểm tra hợp đồng của 3 shape đồng đội đã merge.
  - Thiết kế và sinh khung bộ test `test_ledger_and_evaluation.py`, cài đặt thuật toán thống kê thư viện chuẩn trong `bonus/stats.py`, `bonus/b4_shapes.py`, `test_bonus_b4.py`, và biên tập các báo cáo phân tích theo đúng mẫu.
- **Cách tự kiểm tra kết quả**:
  - Chạy trực tiếp `pytest -q`, `pytest -q tests/test_ledger_and_evaluation.py`, `pytest -q tests/test_bonus_b4.py`, `lab8.crash_test`, `lab8.benchmark`, `bonus.run_b4`, và `lab8.check_submission` trên máy cục bộ.
  - Đối chiếu thủ công các công thức exact McNemar (`2 * sum comb(n, i) * 0.5^n`), paired sign test và tất cả con số trong `ADR` / `Research Card` / `Bonus Report` khớp từng chữ số với `src/reports/benchmark.json` và `src/reports/bonus_ablation.json`.

## 6. Tự đánh giá

- Hoàn thành đầy đủ trách nhiệm kiểm định `ledger + evaluation`, giữ nguyên toàn bộ file hệ thống bị cấm sửa, bổ sung kiểm thử thực chất cho các ca biên và làm thêm trọn vẹn Bonus B4 với số liệu định lượng tái lập được.
- Điểm cần theo dõi tiếp trước khi chốt nộp: nhắc hai thành viên còn lại (`Kien` và `Trần Quang Nam`) hoàn tất dòng trong `TEAM.md` và test/báo cáo còn thiếu (riêng `Kien`), cập nhật `Commit hash` cuối vào `TEAM.md` và `decision_adr.md` sau khi commit chốt, và chạy tự kiểm `student_drop/` ngay khi được phát.
