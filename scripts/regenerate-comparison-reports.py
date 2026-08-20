#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from granular_mean.report import rewrite_archived_comparison_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate archived self-contained comparison reports from "
            "their deterministic metrics and embedded representative images."
        )
    )
    parser.add_argument(
        "reports",
        nargs="+",
        type=Path,
        help="Existing evaluation/comparison.html files to regenerate.",
    )
    args = parser.parse_args()

    for report in args.reports:
        report = report.resolve()
        details = report.with_name("details.json")
        if not details.is_file():
            parser.error(f"deterministic metrics not found: {details}")
        output = rewrite_archived_comparison_report(details, report)
        run_report = report.with_name("run-report.html")
        if run_report.is_file():
            rendered = run_report.read_text()
            old_link = f'href="{report.name}"'
            new_link = f'href="{output.name}"'
            if old_link not in rendered and new_link not in rendered:
                parser.error(
                    f"comparison link not found in run report: {run_report}"
                )
            run_report.write_text(rendered.replace(old_link, new_link))
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
