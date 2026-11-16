# Team

## Thông tin nhóm

- Tên nhóm: VIncon
- Lớp: L3A
- Repo nhóm: `K5-L3A-DAY08-VinCon-FromWorkflowstoAgents` (xem [SUBMISSION.md](SUBMISSION.md))
- URL repo, nhánh nộp, commit chốt: `https://github.com/LysLama/K5-L3A-DAY08-VinCon-FromWorkflowstoAgents` · nhánh `main` · `68ea107`

## Thành viên

| STT | Họ tên          | MSSV        | Email                        | GitHub       | Vai trò                          |
| --: | --------------- | ----------- | ---------------------------- | ------------ | -------------------------------- |
| 1   | Nguyễn Văn Ba   | 2A202603489 | nguyenvanba.tinhoc@gmail.com | xtraiter     | Orchestrator + handoff (shape C) |
| 2   | Lý Thanh Lâm    | 2A202603475 | thanhlam211204@gmail.com     | lyslama      | Ledger + evaluation (+ Bonus B4) |
| 3   | Trần Quang Nam  | 2A202603516 | wgnam2k4@gmail.com           | wgnamlabs    | Single agent (shape B)           |
| 4   | Phạm Trung Kiên | 2A202603479 | trungkienpham0607@gmail.com  | kienpham0607 | Workflow + integration (shape A) |

Gợi ý chia vai:

- Nhóm 6 người: integration; workflow; single agent; orchestrator; ledger/policy/crash; eval/report.
- Nhóm 4 người: workflow + integration; single; orchestrator + handoff; ledger + evaluation.

## Bảng đóng góp

`python -m lab8.check_submission` đọc bảng này bằng máy: giữ nguyên tiêu đề `## Bảng đóng góp` và các cột. Mỗi người một dòng: commit có nội dung và ít nhất một test đã thêm hoặc sửa.

| Người | Vai | Commit | Test đã thêm hoặc sửa |
| --- | --- | --- | --- |
| Nguyễn Văn Ba | Orchestrator + handoff (shape C) | `63053c5`, `63ab3a1` | `src/tests/test_orchestrator_handoff.py`, `src/tests/test_run_claim_never_raises.py` |
| Lý Thanh Lâm | Ledger + evaluation (+ Bonus B4) | `68ea107` | `src/tests/test_ledger_and_evaluation.py`, `src/tests/test_bonus_b4.py` |
| Trần Quang Nam | Single agent (shape B) | `451e3fa` | `src/tests/test_single_agent.py` |
| Phạm Trung Kiên | Workflow + integration (shape A) | `1d00761` | `src/tests/test_workflow_shape.py` |

## Cá nhân

Mỗi thành viên đồng thời tạo một báo cáo riêng trong `report/` theo dạng:

```text
report/team/MSSV_HoTen.md
```

Ví dụ: `report/team/20241234_NguyenVanAn.md`.

Sao chép mục dưới đây cho từng thành viên.

## 2A202603479_PhamTrungKien

### Phần việc phụ trách

- Shape A — deterministic workflow (`src/lab8/shapes/workflow.py`)
- Integration: chữ ký `run_claim`, `finish` / trace mọi nhánh, full quote + `crash_at`
- Báo cáo cá nhân: `report/team/2A202603479_PhamTrungKien.md`
- Tài liệu giải thích: `docs/huong_dan_workflow.md`

### Đóng góp cụ thể

- Commit `1d00761` — triển khai workflow (CP2 + CP3): đọc claim/order, quote từ DB, gọi host, crash an toàn
- Thêm `src/tests/test_workflow_shape.py` (T01 resolve, T02 không tin ticket, secret/PII, needs_info, T13 full quote)
- Ma trận student `-k workflow`: 62 passed

### Bằng chứng

- `python -m pytest -q tests/test_workflow_shape.py`
- `python -m pytest -q -m student -o addopts= -k workflow`
- Báo cáo: `report/team/2A202603479_PhamTrungKien.md`
