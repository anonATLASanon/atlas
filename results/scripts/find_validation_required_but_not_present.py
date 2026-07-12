#!/usr/bin/env python3
"""Find validation rows where required data loading/cleanup is missing."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS}

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


def column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter.upper()) - ord("A") + 1
    return index - 1


def normalize(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text


def is_true(value: object) -> bool:
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def read_shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []

    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("main:si", NS):
        strings.append("".join(text.text or "" for text in item.findall(".//main:t", NS)))
    return strings


def read_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    value = cell.find("main:v", NS)
    if value is None or value.text is None:
        inline = cell.find("main:is", NS)
        if inline is None:
            return ""
        return "".join(text.text or "" for text in inline.findall(".//main:t", NS))

    raw = value.text
    if cell.attrib.get("t") == "s":
        return shared_strings[int(raw)]
    return raw


def read_sheet_rows(
    workbook: ZipFile, sheet_path: str, shared_strings: list[str]
) -> Iterable[list[str]]:
    root = ET.fromstring(workbook.read(sheet_path))
    for row in root.findall(".//main:sheetData/main:row", NS):
        values: list[str] = []
        for cell in row.findall("main:c", NS):
            ref = cell.attrib.get("r", "")
            index = column_index(ref) if ref else len(values)
            while len(values) <= index:
                values.append("")
            values[index] = read_cell_value(cell, shared_strings)
        yield values


def sheet_paths(workbook: ZipFile) -> list[tuple[str, str]]:
    root = ET.fromstring(workbook.read("xl/workbook.xml"))
    rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rels = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }

    sheets: list[tuple[str, str]] = []
    for sheet in root.findall("main:sheets/main:sheet", NS):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
        target = rels[rel_id]
        path = target.lstrip("/")
        if not path.startswith("xl/"):
            path = f"xl/{path}"
        sheets.append((name, path))
    return sheets


def cell(row: list[str], indexes: dict[str, int], column: str) -> str:
    index = indexes[column]
    return normalize(row[index] if index < len(row) else "")


def final_value(row: list[str], indexes: dict[str, int], field: str) -> str:
    corrected = cell(row, indexes, f"review; {field}; corrected_value")
    predicted = cell(row, indexes, f"label; {field}")
    return corrected or predicted


def missing_reason(location: str, mechanism: str) -> str:
    missing = []
    if location in MISSING_VALUES:
        missing.append("location")
    if mechanism in MISSING_VALUES:
        missing.append("mechanism")
    return " and ".join(missing)


def required_columns() -> set[str]:
    columns = {
        "test_id",
        "label; is_integration_test",
        "review; is_integration_test; corrected_value",
    }
    for fields in KINDS.values():
        for field in fields.values():
            columns.add(f"label; {field}")
            columns.add(f"review; {field}; corrected_value")
    return columns


def find_cases(workbook_path: Path, *, integration_only: bool) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    required = required_columns()

    with ZipFile(workbook_path) as workbook:
        shared_strings = read_shared_strings(workbook)
        for application, sheet_path in sheet_paths(workbook):
            rows = iter(read_sheet_rows(workbook, sheet_path, shared_strings))
            try:
                header = next(rows)
            except StopIteration:
                continue

            missing_columns = sorted(required - set(header))
            if missing_columns:
                raise ValueError(
                    f"{application}: missing required columns: {', '.join(missing_columns)}"
                )

            indexes = {name: index for index, name in enumerate(header)}
            for row in rows:
                is_integration = is_true(final_value(row, indexes, "is_integration_test"))
                if integration_only and not is_integration:
                    continue

                test_id = cell(row, indexes, "test_id")
                for kind, fields in KINDS.items():
                    required_value = final_value(row, indexes, fields["required"])
                    if not is_true(required_value):
                        continue

                    location = final_value(row, indexes, fields["location"])
                    mechanism = final_value(row, indexes, fields["mechanism"])
                    if mechanism == "not_needed":
                        continue

                    reason = missing_reason(location, mechanism)
                    if not reason:
                        continue

                    cases.append(
                        {
                            "application": application,
                            "test_id": test_id,
                            "kind": kind,
                            "is_integration_test": str(is_integration).lower(),
                            "required": required_value,
                            "location": location,
                            "mechanism": mechanism,
                            "missing": reason,
                        }
                    )

    return cases


def write_cases_csv(output_path: Path, cases: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "application",
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
        key = (case["application"], case["kind"], case["missing"])
        counts[key] = counts.get(key, 0) + 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("application", "kind", "missing", "count"),
        )
        writer.writeheader()
        for (application, kind, missing), count in sorted(counts.items()):
            writer.writerow(
                {
                    "application": application,
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
            "Find rows where data load or cleanup is required but the final "
            "location/mechanism is not_present or blank."
        )
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=default_results_dir / "validation_dataset.xlsx",
        help="Path to the validation workbook.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_results_dir / "required_but_not_present",
        help="Directory for result CSV files.",
    )
    parser.add_argument(
        "--integration-only",
        action="store_true",
        help="Only include rows whose final is_integration_test value is true.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = find_cases(args.workbook, integration_only=args.integration_only)

    suffix = "integration_tests" if args.integration_only else "all_tests"
    cases_csv = args.output_dir / f"required_but_not_present_{suffix}.csv"
    summary_csv = args.output_dir / f"required_but_not_present_summary_{suffix}.csv"
    write_cases_csv(cases_csv, cases)
    write_summary_csv(summary_csv, cases)

    print(f"Cases found: {len(cases)}")
    print(f"Cases CSV: {cases_csv}")
    print(f"Summary CSV: {summary_csv}")


if __name__ == "__main__":
    main()
