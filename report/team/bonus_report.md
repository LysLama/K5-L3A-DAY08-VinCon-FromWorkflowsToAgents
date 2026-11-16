# Bonus report: B4

- Topic + nguồn (tên, năm, slide): **B4 · Baseline công bằng, ablation và thống kê** — EMNLP 2026 (*Rethinking Evaluation of MAS Efficiency*, slide 44, 59) và AgentArch, AACL 2026 (slide 43).
- CLAIM của nguồn (1 câu): "Efficiency gain" có thể đến từ cách thiết kế benchmark (baseline chưa tối ưu hoặc biến thể giữ thành phần thừa), đôi khi random pruning vẫn giữ nguyên hiệu năng, nên cần so với single-agent/baseline đơn giản trong cùng runtime, model và tool kèm kiểm định thống kê.
- BOUNDARY (model / dataset / setup): Thực nghiệm trên LogiX-VN với `MockLLM` cố định theo seed (`11,22,33,44,55`), 14 public claims × 5 seed = 70 trial/shape (`data/public_claims.jsonl`, `data/public_world_state.json`), giá mô phỏng `config/pricing.yaml`, `as_of = 2026-11-15`, `latency: unavailable`.
- HYPOTHESIS trên LogiX: (H1) Baseline thuần luật `rules_only` (0 model call) đạt cùng `pass_rate = 1.000` với chi phí thấp hơn mọi shape dùng agent; (H2) Bỏ thành phần không tham gia quyết định ghi tiền (`draft` của `workflow` hoặc investigator thứ hai `check_prior_refunds` của `orchestrator`) không làm giảm `pass_rate` nhưng giảm đáng kể `cost/success`; (H3) `swarm_pruned` (bỏ ngẫu nhiên `peer`/`parse` theo seed) giữ hoặc cải thiện `pass_rate` với chi phí thấp hơn `swarm`.
- Biến cố định / biến thay đổi: Cố định corpus, world, `MockLLM`, danh sách tool, host gate `durability.issue_refund`, 5 seed, bảng giá và evaluator `lab8.metrics`; biến duy nhất thay đổi là topology / bật-tắt thành phần (`src/bonus/b4_shapes.py`).
- Lệnh tái lập (copy-paste được):
  - Thống kê & ablation đầy đủ (chạy trong `src/`): `python -m bonus.run_b4 --out reports/bonus_ablation.json`
  - Chạy qua cổng `--extra-shape` chính thức (chạy trong `src/`): `python -m lab8.benchmark --shapes workflow,single,orchestrator,swarm,rules_only,swarm_pruned,workflow_trust_ticket,orchestrator_no_history_inv --extra-shape rules_only=bonus.b4_shapes:rules_only --extra-shape swarm_pruned=bonus.b4_shapes:swarm_pruned --extra-shape workflow_trust_ticket=bonus.b4_shapes:workflow_trust_ticket --extra-shape orchestrator_no_history_inv=bonus.b4_shapes:orchestrator_no_history_inv --cases data/public_claims.jsonl --seeds 11,22,33,44,55 --out reports/bonus_benchmark.json`
  - Unit tests: `python -m pytest -q tests/test_bonus_b4.py` (`13 passed`)
- File report + run id: `src/reports/bonus_ablation.json`, `src/reports/bonus_benchmark.json`; run id minh họa: `R-rules_only-C-001-s11`, `R-orchestrator_no_history_inv-C-014-s11`, `R-swarm_pruned-C-002-s55`, `R-workflow_trust_ticket-C-002-s11`.

## Kết quả

Số liệu trích nguyên từ `src/reports/bonus_ablation.json` (cluster bootstrap `n_boot = 2000`, `seed = 42` resample theo `claim_id`, `n_claims = 14`, `n_trials = 70` mỗi shape; safety counts kiểm trực tiếp từ trace và ledger):

| Shape / Biến thể | Pass rate | 95% Bootstrap CI (theo claim) | Pass^5 | Seed variance | Cost/success (VND) | Mean steps | Approval bypass | Secret leak |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `rules_only` (baseline 0 LLM) | 1.000 | [1.000, 1.000] | 1.000 | 0.000000 | **27.86** | 3.50 | 0 | 0 |
| `workflow` (shape chọn) | 1.000 | [1.000, 1.000] | 1.000 | 0.000000 | 28.79 | 2.86 | 0 | 0 |
| `workflow_trust_ticket` | 0.929 | [0.786, 1.000] | 0.929 | 0.000000 | 31.01 | 3.64 | 0 | 0 |
| `single` | 1.000 | [1.000, 1.000] | 1.000 | 0.000000 | 39.08 | 5.64 | 0 | 0 |
| `orchestrator` | 1.000 | [1.000, 1.000] | 1.000 | 0.000000 | 54.65 | 8.29 | 0 | 0 |
| `orchestrator_no_history_inv` | 1.000 | [1.000, 1.000] | 1.000 | 0.000000 | 39.14 | 4.43 | 0 | 0 |
| `swarm` | 0.986 | [0.957, 1.000] | 0.929 | 0.000816 | 49.57 | 2.80 | 0 | 0 |
| `swarm_pruned` (baseline 2) | 1.000 | [1.000, 1.000] | 1.000 | 0.000000 | 48.07 | 3.43 | 0 | 0 |

Kiểm định cặp trên cùng 70 cặp `(claim_id, seed)` (cài bằng thư viện chuẩn trong `src/bonus/stats.py`):
- `workflow` vs `swarm`: McNemar `a_only=1, b_only=0, p = 1.0000` (chưa đủ ý nghĩa thống kê về độ chính xác ở `N=14` claim); cost sign test `-20.07 VND/trial` (`p = 1.69e-21`).
- `workflow` vs `rules_only`: McNemar `p = 1.0000`; cost sign test `+0.93 VND/trial` (`p = 1.69e-21`). Bỏ `draft` LLM không đổi bất kỳ quyết định nghiệp vụ nào.
- `workflow` vs `single` / `orchestrator`: McNemar `p = 1.0000`; cost sign test lần lượt `-10.29 VND` (`p = 5.42e-20`) và `-25.86 VND` (`p = 1.69e-21`).
- `orchestrator` vs `orchestrator_no_history_inv`: McNemar `p = 1.0000` (pass cả T13, T14); cost sign test `+15.51 VND` (`p = 5.42e-20`, giảm 28.4% chi phí) vì host đã tự đọc lại tổng hoàn tiền của đơn trong transaction `issue_refund`.
- `workflow` vs `workflow_trust_ticket`: McNemar `a_only=5, b_only=0, p = 0.0625` (5/5 seed sai trên `C-002`).
- `swarm` vs `swarm_pruned`: McNemar `a_only=0, b_only=1, p = 1.0000`; cost sign test `+0.79 VND` (`p = 4.44e-16`), `swarm_pruned` tránh được lỗi parse sai của `swarm` ở `(C-002, 55)`.

## Kết luận

Kết quả thực nghiệm **ủng hộ các claim của EMNLP 2026 và AgentArch (AACL 2026)** trong phạm vi bài toán LogiX-VN:
1. Chênh lệch `pass_rate` giữa `workflow` (`1.000`) và `swarm` (`0.986`) trên bộ public chưa đạt mức ý nghĩa thống kê (`McNemar p = 1.0000`, 95% CI giao nhau hoàn toàn `[1.000, 1.000]` vs `[0.957, 1.000]`), nhưng **chênh lệch chi phí** (`28.79` vs `49.57 VND/success`, `p = 1.69e-21`) lại cực kỳ rõ rệt — chứng minh không thể chỉ nhìn vào nhãn kiến trúc multi-agent để kết luận hiệu quả.
2. Hai thành phần có thể cắt bỏ mà `pass_rate` vẫn giữ nguyên `1.000` là lời gọi `draft` LLM của `workflow` (`rules_only` giảm còn `27.86 VND`) và investigator thứ hai `check_prior_refunds` của `orchestrator` (`orchestrator_no_history_inv` giảm từ `54.65` xuống `39.14 VND`). Ngược lại, cắt bước đối chiếu DB `delay_days` làm tụt ngay hiệu năng xuống `0.929`.
3. `swarm_pruned` đạt `1.000` và rẻ hơn `swarm` (`48.07` vs `49.57`) vì random pruning tình cờ loại bỏ lệnh `parse` gây lỗi ở seed `55`.
- **Điều kiện kết luận đảo ngược**: Nếu `swarm_pruned` bị gài một seed khiến `parse` không bị cắt tại đúng ca `REFERENCE_WEAKNESS` thì `pass_rate` sẽ quay lại `0.986`; hoặc nếu chuyển sang tác vụ yêu cầu hiểu ngôn ngữ tự nhiên phi cấu trúc không có cột DB đối chiếu, `rules_only` sẽ tụt mạnh và LLM reasoning mới mang lại chênh lệch có ý nghĩa thống kê.

## Giới hạn

`MockLLM` chỉ sinh chuỗi tất định theo hash/regex chứ không phản ánh năng lực suy luận hay phân phối lỗi thật của LLM sản xuất; `latency` bị khóa ở `unavailable` nên chưa đo được trade-off thời gian thực; cỡ mẫu `N=14` claim public nhỏ khiến ngay cả lỗi lặp lại 5/5 seed trên 1 claim (`workflow` vs `workflow_trust_ticket`) chỉ đạt `McNemar p = 0.0625 > 0.05`.
