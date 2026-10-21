from __future__ import annotations

import argparse
import json
from pathlib import Path

from insightpilot.verification.evaluation import load_evaluation_cases, run_verification_evaluation


def main() -> int:
    """Chạy bộ đánh giá xác minh và in chỉ số ra terminal."""
    parser = argparse.ArgumentParser(
        description="Đánh giá cục bộ các bộ kiểm tra số học và độ bao phủ claim của InsightPilot."
    )
    parser.add_argument(
        "--dataset",
        default="data/verification_evaluation.json",
        help="Đường dẫn tới tệp JSON chứa các tình huống đánh giá.",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Đường dẫn tùy chọn để lưu báo cáo kết quả dạng JSON.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Trả mã thoát khác 0 nếu có tình huống phân loại sai.",
    )
    args = parser.parse_args()

    cases = load_evaluation_cases(args.dataset)
    report = run_verification_evaluation(cases)

    print(f"Số tình huống: {len(report.results)}")
    print(f"Phân loại đúng: {report.passed_count}")
    print(f"Phân loại sai: {report.failed_count}")
    print("\nChỉ số tổng thể:")
    for name, value in report.overall.to_dict().items():
        print(f"  {name}: {value}")

    print("\nTheo thành phần:")
    for component, metrics in report.by_component.items():
        print(f"  {component}:")
        for name, value in metrics.to_dict().items():
            print(f"    {name}: {value}")

    if report.failed_count:
        print("\nCác tình huống phân loại sai:")
        for result in report.results:
            if not result.passed:
                print(
                    f"  - {result.case_id}: mong đợi issue={result.expected_issue}, "
                    f"phát hiện issue={result.detected_issue} ({result.actual_status})"
                )

    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nĐã lưu báo cáo: {output_path}")

    # Chế độ mặc định chỉ báo cáo; --strict hữu ích khi dùng trong CI.
    return 1 if args.strict and report.failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
