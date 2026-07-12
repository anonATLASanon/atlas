#!/usr/bin/env python3
"""Find full-dataset JSON records where required data loading/cleanup is missing."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


KINDS = {
    "data_load": {
        "required": "data_load_mechanism_is_required",
        "location": "data_load_location",
        "mechanism": "data_load_mechanism",
    },
    "data_cleanup": {
        "required": "data_cleanup_mechanism_is_required",
        "location": "data_cleanup_location",
        "mechanism": "data_cleanup_mechanism",
    },
}

MISSING_VALUES = {"", "not_present"}


def normalize(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text


def is_true(value: object) -> bool:
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def final_label_for(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    final_label = value.get("final_label")
    if isinstance(final_label, dict):
        return final_label
    return None


def missing_reason(location: str, mechanism: str) -> str:
    missing = []
    if location in MISSING_VALUES:
        missing.append("location")
    if mechanism in MISSING_VALUES:
        missing.append("mechanism")
    return " and ".join(missing)


def find_cases(labels_dir: Path, *, integration_only: bool) -> tuple[list[dict[str, str]], int]:
    json_files = sorted(labels_dir.glob("*.json"), key=lambda path: path.stem.lower())
    if not json_files:
        raise ValueError(f"No JSON files found in {labels_dir}")

    cases: list[dict[str, str]] = []
    skipped_without_final_label = 0

    for json_path in json_files:
        project = json_path.stem
        with json_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"{json_path} must contain a JSON object")

        for test_id, record in payload.items():
            final_label = final_label_for(record)
            if final_label is None:
                skipped_without_final_label += 1
                continue

            is_integration = is_true(final_label.get("is_integration_test"))
            if integration_only and not is_integration:
                continue

            for kind, fields in KINDS.items():
                required = final_label.get(fields["required"])
                if not is_true(required):
                    continue

                location = normalize(final_label.get(fields["location"]))
                mechanism = normalize(final_label.get(fields["mechanism"]))
                if mechanism == "not_needed":
                    continue

                reason = missing_reason(location, mechanism)
                if not reason:
                    continue

                cases.append(
                    {
                        "project": project,
                        "test_id": str(test_id),
                        "kind": kind,
                        "is_integration_test": str(is_integration).lower(),
                        "required": normalize(required),
                        "location": location,
                        "mechanism": mechanism,
                        "missing": reason,
                    }
                )

    return cases, skipped_without_final_label


def write_cases_csv(output_path: Path, cases: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "project",
                "test_id",
                "kind",
                "is_integration_test",
                "required",
                "location",
                "mechanism",
                "missing",
            ),
        )
        writer.writeheader()
        writer.writerows(cases)


def write_summary_csv(output_path: Path, cases: list[dict[str, str]]) -> None:
    counts: dict[tuple[str, str, str], int] = {}
    for case in cases:
        key = (case["project"], case["kind"], case["missing"])
        counts[key] = counts.get(key, 0) + 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("project", "kind", "missing", "count"),
        )
        writer.writeheader()
        for (project, kind, missing), count in sorted(counts.items()):
            writer.writerow(
                {
                    "project": project,
                    "kind": kind,
                    "missing": missing,
                    "count": count,
                }
            )


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    default_results_dir = script_path.parents[1]

    parser = argparse.ArgumentParser(
        description=(
            "Find JSON label records where data load or cleanup is required but "
            "the final location/mechanism is not_present or blank."
        )
    )
    parser.add_argument(
        "--labels-dir",
        type=Path,
        default=default_results_dir / "labels_full_dataset",
        help="Directory containing full-dataset JSON label files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_results_dir / "required_but_not_present_full_dataset",
        help="Directory for result CSV files.",
    )
    parser.add_argument(
        "--integration-only",
        dest="integration_only",
        action="store_true",
        default=True,
        help="Only include records whose final is_integration_test value is true. This is the default.",
    )
    parser.add_argument(
        "--all-tests",
        dest="integration_only",
        action="store_false",
        help="Include all records, regardless of final is_integration_test value.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.labels_dir.exists():
        raise FileNotFoundError(f"Labels directory not found: {args.labels_dir}")

    cases, skipped_without_final_label = find_cases(
        args.labels_dir,
        integration_only=args.integration_only,
    )

    suffix = "integration_tests" if args.integration_only else "all_tests"
    cases_csv = args.output_dir / f"required_but_not_present_{suffix}.csv"
    summary_csv = args.output_dir / f"required_but_not_present_summary_{suffix}.csv"
    write_cases_csv(cases_csv, cases)
    write_summary_csv(summary_csv, cases)

    print(f"Projects scanned: {len(list(args.labels_dir.glob('*.json')))}")
    print(f"Records skipped without final_label: {skipped_without_final_label}")
    print(f"Cases found: {len(cases)}")
    print(f"Cases CSV: {cases_csv}")
    print(f"Summary CSV: {summary_csv}")


if __name__ == "__main__":
    main()
