# Research card

File này nằm cố định ở `report/team/research_card.md`; `python -m lab8.check_submission` đọc cột "Nhóm điền" bằng máy.

Phần này nối tiếp phần mini research ở buổi lý thuyết (slide 62–63). Chọn **một** câu R1–R4, điền 6 dòng, rồi biến nó thành **một ablation** chạy được trong lab: giữ nguyên model (MockLLM), tool, seed, corpus và giá, chỉ thay đổi một biến.

| Câu | Nguồn (thư viện tham khảo, slide 68–69) | Câu hỏi gợi ý cho lab |
| --- | --- | --- |
| R1 · Scaling | Google Research 2026, *Towards a Science of Scaling Agent Systems* | Task claims chủ yếu tuần tự hay song song được? Dự đoán thêm investigator sẽ làm pass rate và cost/success thay đổi thế nào. |
| R2 · Failure taxonomy | MAST, NeurIPS 2025, *Why Do Multi-Agent LLM Systems Fail?* | Các trial fail của swarm (seed 55) thuộc nhóm nào: lỗi giao việc, lệch mục tiêu, hay lỗi kiểm chứng? |
| R3 · Architecture choices | AgentArch, AACL 2026 | Nếu đổi topology mà giữ nguyên mọi thứ khác, biến nào phải cố định để kết luận còn đúng? |
| R4 · Evaluation confounders | EMNLP 2026, *Rethinking Evaluation of MAS Efficiency* | Làm sao chứng minh chênh lệch giữa A/B/C/D là do topology, không phải do prompt, tool hay seed? |

## Phiếu của nhóm

Điền vào cột cuối. Không xóa hai cột đầu.

| Field | Hướng dẫn | Nhóm điền |
| --- | --- | --- |
| CÂU | R1 / R2 / R3 / R4 | R4 · Evaluation confounders |
| SOURCE | Paper/blog, năm, URL, loại bằng chứng (benchmark, production report, blog kinh nghiệm) | EMNLP 2026, *Rethinking Evaluation of MAS Efficiency* (slide 44, 59); đối chiếu cùng AgentArch, AACL 2026 (slide 43) — tài liệu bài giảng N8 / benchmark thực nghiệm |
| CLAIM | Một kết luận gốc của nguồn. Không viết rộng hơn phạm vi paper | "Efficiency gain" trong đánh giá hệ multi-agent có thể đến từ thiết kế benchmark hoặc giữ các thành phần thừa; phải đối chứng với baseline đơn giản và chạy ablation có kiểm định thống kê trong cùng runtime, model và tool |
| BOUNDARY | Model / dataset / setup giới hạn kết luận đó | Áp dụng trong sandbox LogiX-VN với `MockLLM` cố định theo seed, 14 public claims × 5 seed (`11,22,33,44,55`), giá mô phỏng `config/pricing.yaml`, `as_of = 2026-11-15`, `latency: unavailable` |
| HYPOTHESIS | Nếu đổi shape A→B (hoặc bật/tắt một thành phần), metric X sẽ đổi theo hướng nào, khoảng bao nhiêu | Khi giữ cố định model/tool/seed/giá: (1) bỏ lời gọi `draft` LLM khỏi `workflow` (`rules_only`) hoặc bỏ investigator thứ hai `check_prior_refunds` khỏi `orchestrator` (`orchestrator_no_history_inv`) sẽ giữ nguyên `pass_rate = 1.000` nhưng giảm `cost/success` (khoảng 1 VND với `workflow` và ~15 VND với `orchestrator`); (2) bỏ kiểm chứng DB delay (`workflow_trust_ticket`) sẽ làm tụt `pass_rate` do lỗi C-002 |
| METHOD | Biến giữ cố định: model, tools, seed, corpus, giá, evaluator. Biến duy nhất được thay đổi: … | Biến giữ cố định: `MockLLM`, read/write tools & host gate `durability.issue_refund`, seeds `11,22,33,44,55`, corpus `data/public_claims.jsonl`, `config/pricing.yaml`, evaluator `lab8.metrics`. Biến duy nhất thay đổi: bật/tắt từng thành phần (`rules_only`, `workflow_trust_ticket`, `orchestrator_no_history_inv`, `swarm_pruned`) |
| FAILURE / METRIC | Một lỗi dự kiến và cách đo nó: pass rate, pass^5, variance, cost/success, leak, bypass | Lỗi dự kiến khi bỏ DB grounding (`workflow_trust_ticket`) hoặc khi `swarm` tin ticket ở seed 55 tại `C-002`: trả nhầm `resolved` (20.000 VND) thay vì `denied`. Đo bằng `pass_rate` (cluster bootstrap 95% CI theo `claim_id`), `pass^5`, `seed_variance`, `cost_per_success_vnd`, paired McNemar, paired cost sign test, `approval_bypass_count`, `secret_leak_count` |

## Kết quả ablation

- Lệnh đã chạy (copy nguyên văn): `python -m bonus.run_b4 --out reports/bonus_ablation.json`
- Run id / file report: `src/reports/bonus_ablation.json` và `src/reports/bonus_benchmark.json` (minh họa cặp: `R-workflow-C-002-s55`, `R-orchestrator-C-014-s11`, `R-orchestrator_no_history_inv-C-014-s11`, `R-swarm_pruned-C-002-s55`)
- Kết quả so với hypothesis (đúng / sai / không kết luận được), kèm số liệu: **Ủng hộ giả thuyết** trên cả 3 nhánh kiểm thử:
  1. `workflow` (`1.000`, `28.79 VND`) vs `rules_only` (`1.000`, `27.86 VND`): bỏ lời gọi `draft` giữ nguyên pass rate (`McNemar p = 1.0000`) và giảm chi phí `-0.93 VND/trial` (`sign test p = 1.69e-21`).
  2. `orchestrator` (`1.000`, `54.65 VND`) vs `orchestrator_no_history_inv` (`1.000`, `39.14 VND`): bỏ investigator thứ hai không làm đổi pass rate ở cả T13/T14 (`McNemar p = 1.0000`) vì host tự trừ trần trong transaction ghi, nhưng giảm chi phí `-15.51 VND/trial` (`-28.4%`, `sign test p = 5.42e-20`).
  3. `workflow` (`1.000`, 95% CI `[1.000, 1.000]`) vs `workflow_trust_ticket` (`0.929`, 95% CI `[0.786, 1.000]`): bỏ kiểm chứng DB delay làm `C-002` fail cả 5 seed (`McNemar a_only=5, b_only=0, p = 0.0625` do cỡ mẫu nhỏ `N=14` claim). Ngoài ra `swarm_pruned` (`1.000`, `48.07 VND`) vừa rẻ hơn vừa tránh được lỗi `C-002` seed `55` của `swarm` (`0.986`, `49.57 VND`). Tất cả biến thể đều có `approval_bypass = 0`, `secret_leak = 0`.
- Giới hạn: MockLLM không phải model sản xuất, latency là `unavailable`, và cỡ mẫu public `N=14` claim khiến ngay cả lỗi tất định 5/5 trên 1 claim mới cho `McNemar p = 0.0625 > 0.05`.

Muốn đi xa hơn một ablation để lấy điểm cộng thì xem [docs/bonus_topics.md](../../docs/bonus_topics.md).
