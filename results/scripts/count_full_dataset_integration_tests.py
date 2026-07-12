#!/usr/bin/env python3
"""Count integration-test percentages in full-dataset JSON label files."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ApplicationSummary:
    application: str
    labeled_rows: int
    integration_tests: int
    integration_percentage: str


def normalize(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text


def is_true(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def is_false(value: object) -> bool:
    if isinstance(value, bool):
        return not value
    return normalize(value).lower() in {"0", "false", "no", "n"}


def percentage(integration_tests: int, labeled_rows: int) -> str:
    if not labeled_rows:
        return "N/A"
    return f"{integration_tests / labeled_rows * 100:.2f}%"


def application_name(path: Path) -> str:
    name = path.stem
    if "_" not in name:
        return name
    return name.split("_", 1)[1]


def summarize_file(path: Path) -> ApplicationSummary:
    with path.open() as handle:
        records: Any = json.load(handle)

    if not isinstance(records, dict):
        raise ValueError(f"{path}: expected top-level JSON object")

    labeled_rows = 0
    integration_tests = 0

    for test_id, record in records.items():
        if not isinstance(record, dict):
            raise ValueError(f"{path}: {test_id}: expected object record")

        final_label = record.get("final_label")
        if not isinstance(final_label, dict):
            continue

        value = final_label.get("is_integration_test")
        if is_true(value):
            labeled_rows += 1
            integration_tests += 1
        elif is_false(value):
            labeled_rows += 1

    return ApplicationSummary(
        application=application_name(path),
        labeled_rows=labeled_rows,
        integration_tests=integration_tests,
        integration_percentage=percentage(integration_tests, labeled_rows),
    )


def read_dataset(directory: Path) -> list[ApplicationSummary]:
    paths = sorted(directory.glob("*.json"), key=lambda path: application_name(path).lower())
    if not paths:
        raise ValueError(f"{directory}: no JSON files found")
    summaries = [summarize_file(path) for path in paths]
    return sorted(summaries, key=lambda summary: summary.application.lower())


def overall_summary(summaries: list[ApplicationSummary]) -> ApplicationSummary:
    labeled_rows = sum(summary.labeled_rows for summary in summaries)
    integration_tests = sum(summary.integration_tests for summary in summaries)

    return ApplicationSummary(
        application="Overall",
        labeled_rows=labeled_rows,
        integration_tests=integration_tests,
        integration_percentage=percentage(integration_tests, labeled_rows),
    )


def print_table(summaries: list[ApplicationSummary]) -> None:
    fields = (
        "application",
        "labeled_rows",
        "integration_tests",
        "integration_percentage",
    )
    rows = [
        [str(getattr(summary, field)) for field in fields]
        for summary in [*summaries, overall_summary(summaries)]
    ]
    widths = [
        max(len(field), *(len(row[index]) for row in rows))
        for index, field in enumerate(fields)
    ]

    print("  ".join(field.ljust(widths[index]) for index, field in enumerate(fields)))
    print("  ".join("-" * width for width in widths))
    for row in rows[:-1]:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    print("  ".join("-" * width for width in widths))
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(rows[-1])))


def write_csv(path: Path, summaries: list[ApplicationSummary]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(ApplicationSummary.__dataclass_fields__),
        )
        writer.writeheader()
        for summary in summaries:
            writer.writerow(summary.__dict__)
        writer.writerow(overall_summary(summaries).__dict__)


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    default_results_dir = script_path.parents[1]

    parser = argparse.ArgumentParser(
        description=(
            "Calculate the percentage of integration tests for each application "
            "in results/labels_full_dataset JSON files."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=default_results_dir / "labels_full_dataset",
        help="Directory containing full-dataset JSON label files.",
    )
    parser.add_argument("--csv", type=Path, help="Optional path for a CSV summary.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summaries = read_dataset(args.input_dir)
    print_table(summaries)
    if args.csv:
        write_csv(args.csv, summaries)


if __name__ == "__main__":
    main()
