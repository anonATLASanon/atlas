#!/usr/bin/env python3
"""Count integration-test percentages in the validation workbook.

The final is_integration_test value uses the reviewed corrected value when it is
present; otherwise it uses the original label.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile


LABEL_COLUMN = "label; is_integration_test"
REVIEW_STATUS_COLUMN = "review; is_integration_test; status"
CORRECTED_VALUE_COLUMN = "review; is_integration_test; corrected_value"
REQUIRED_COLUMNS = (LABEL_COLUMN, REVIEW_STATUS_COLUMN, CORRECTED_VALUE_COLUMN)

APPLICATION_ORDER = (
    "catwatch",
    "cwa-verification-server",
    "features-service",
    "gestaohospital",
    "proxyprint",
    "languagetool",
    "market",
    "ocvn",
    "genome-nexus",
    "ofbiz",
    "petclinic",
    "shopizer",
)

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS}


@dataclass(frozen=True)
class ApplicationSummary:
    application: str
    labeled_rows: int
    integration_tests: int
    integration_percentage: str


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


def is_false(value: object) -> bool:
    return normalize(value).lower() in {"0", "false", "no", "n"}


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


def percentage(integration_tests: int, labeled_rows: int) -> str:
    if not labeled_rows:
        return "N/A"
    return f"{integration_tests / labeled_rows * 100:.2f}%"


def application_sort_key(application: str) -> tuple[int, str]:
    try:
        return APPLICATION_ORDER.index(application), application
    except ValueError:
        return len(APPLICATION_ORDER), application


def summarize_application(
    application: str,
    rows: Iterable[list[str]],
) -> ApplicationSummary:
    iterator = iter(rows)
    try:
        header = next(iterator)
    except StopIteration as exc:
        raise ValueError(f"{application}: sheet is empty") from exc

    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise ValueError(f"{application}: missing required columns: {', '.join(missing)}")

    label_index = header.index(LABEL_COLUMN)
    corrected_value_index = header.index(CORRECTED_VALUE_COLUMN)

    labeled_rows = 0
    integration_tests = 0

    for row in iterator:
        label = normalize(row[label_index] if label_index < len(row) else "")
        corrected_value = normalize(
            row[corrected_value_index] if corrected_value_index < len(row) else ""
        )

        final_value = corrected_value or label
        if is_true(final_value):
            labeled_rows += 1
            integration_tests += 1
        elif is_false(final_value):
            labeled_rows += 1

    return ApplicationSummary(
        application=application,
        labeled_rows=labeled_rows,
        integration_tests=integration_tests,
        integration_percentage=percentage(integration_tests, labeled_rows),
    )


def read_workbook(path: Path) -> list[ApplicationSummary]:
    with ZipFile(path) as workbook:
        shared_strings = read_shared_strings(workbook)
        summaries = [
            summarize_application(
                application,
                read_sheet_rows(workbook, sheet_path, shared_strings),
            )
            for application, sheet_path in sheet_paths(workbook)
        ]
    return sorted(summaries, key=lambda summary: application_sort_key(summary.application))


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
            "in results/validation_dataset.xlsx."
        )
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=default_results_dir / "validation_dataset.xlsx",
        help="Path to the validation workbook.",
    )
    parser.add_argument("--csv", type=Path, help="Optional path for a CSV summary.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summaries = read_workbook(args.workbook)
    print_table(summaries)
    if args.csv:
        write_csv(args.csv, summaries)


if __name__ == "__main__":
    main()
