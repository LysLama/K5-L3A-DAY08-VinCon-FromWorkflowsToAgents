# Decision record

Điền sau dấu `:` trên cùng dòng, không xóa nhãn. Giảng viên và `python -m lab8.check_submission` (chạy trong `src/`) đọc các dòng này bằng máy. Không đổi tên hay dời file này khỏi `report/team/`.
`Shape chọn` phải là đúng một trong: `workflow`, `single`, `orchestrator`, `swarm`. Đây là shape được chấm cổng hidden.

- Shape chọn: workflow
- Commit hash: 68ea107
- Run id dẫn chứng: R-workflow-C-001-s11, R-workflow-C-014-s11, R-swarm-C-002-s55 (src/reports/benchmark.json)
- Pass rate / pass^5 / seed min-max / variance: 1.000 / 1.000 / 1.000–1.000 / 0.000000
- Cost per success (mô phỏng, VND): 28.79
- Crash safety: 20/20 (src/reports/crash.json)
- Secret leak / approval bypass: 0 / 0

## Vì sao shape này

So trên cùng 14 claim public × 5 seed (`11,22,33,44,55`) với cùng `MockLLM`, cùng `as_of` `2026-11-15` và cùng `config/pricing.yaml` (`src/reports/benchmark.json`), ba kiến trúc `workflow`, `single` và `orchestrator` đều đạt `pass_rate = 1.000` (70/70), `pass^5 = 1.000` và `seed_variance = 0.000000`, trong khi `swarm` đạt `0.986` (69/70, `pass^5 = 0.929`, `variance = 0.000816`) do sai ở `C-002` seed `55` khi tin số ngày trễ trong ticket thay vì cột `delay_days` của đơn hàng. Vì quy trình xử lý claim của LogiX-VN là một luồng kiểm tra xác định (kiểm `order_id` → tra đơn theo principal → tính bồi thường theo policy hiện hành → gọi cửa ghi `durability.issue_refund`), `workflow` đạt độ chính xác tuyệt đối với chi phí mô phỏng thấp nhất (`28.79 VND/success`, so với `39.08` của `single`, `49.57` của `swarm` và `54.65` của `orchestrator`) và ít bước nhất (`2.86` mean steps, `p95 = 3`), tuân thủ nguyên tắc chọn kiến trúc ít tự chủ nhất mà vẫn giải quyết đúng bài toán.

## Có đáng đổi lấy multi-agent không

Không đáng đổi lấy multi-agent trên bài toán hiện tại. Chi phí mô phỏng của `orchestrator` (`54.65 VND/success`) cao hơn `workflow` (`28.79 VND/success`, chênh lệch `+25.86 VND/trial`, paired cost sign test `p = 1.69e-21` trong `src/reports/bonus_ablation.json`) nhưng không mang lại thêm bất kỳ điểm pass nào (`McNemar p = 1.0000`), còn `swarm` vừa đắt hơn (`49.57 VND/success`) vừa xuất hiện dao động theo seed (`seed_variance = 0.000816`). Quyết định chỉ đảo lại sang `single` hoặc `orchestrator` khi dữ liệu đầu vào chuyển sang dạng mở không thể rẽ nhánh bằng code thuần (ví dụ phải tổng hợp nhiều nguồn bằng chứng phi cấu trúc, gọi công cụ đọc có độ trễ lớn chạy song song được, hoặc cần tách hẳn ngữ cảnh nhạy cảm sang worker ở ranh giới trust/deploy khác biệt).

## Trace và bằng chứng

Trace của nhóm (viết qua `lab8.trace.Trace` và kết thúc qua `lab8.shapes.common.finish`) chỉ ghi các event đã qua allowlist: `claim_view` (chỉ gồm `found`, `claim_id`, `has_order_id`), `lookup_order` (chỉ gồm `visible`, `reason`, `order_id`), `quote` (số tiền, `clause_ids`, `parts`), `decision`, và `crash` (khi `InjectedCrash` xảy ra trước khi re-raise). Nhóm cố ý **không** ghi dòng `claims` thô (`parent_secret`, `raw_headers_json`, `ticket`), không ghi `principal_id`, `phone`, `address`, `internal_note`, `item_name`, và ở nhánh lỗi ngoại lệ chỉ ghi `type(exc).__name__` chứ không ghi message ngoại lệ. Để chứng minh không lộ secret ngoài phạm vi scanner mặc định, nhóm chạy `lab8.metrics.check_trace` + `trial_pass` (kiểm tra `CANARY_SECRET_*` và `forbid_substrings` trên cả `trace_path` lẫn mọi file `<run_id>*` cùng thư mục, kể cả ngay tại thời điểm crash trong `src/tests/test_ledger_and_evaluation.py`) và xác nhận toàn bộ các shape chỉ dùng tool đọc theo `tools.manifest.v1.1.yaml`.

## Giới hạn

MockLLM chỉ là hàm giả lập tất định theo seed chứ không phải mô hình ngôn ngữ sản xuất, và `latency` ở mọi báo cáo đều là `unavailable`. Các phép đo public mới phủ 14 claim (nên khác biệt nhỏ như `workflow` vs `swarm` 1/70 trial chưa có ý nghĩa thống kê ở `N=14`, `McNemar p = 1.0000`), cần đối chiếu thêm trên bộ hidden 40 claim × 5 seed của giảng viên mà không sửa tay bất kỳ JSON báo cáo nào.
