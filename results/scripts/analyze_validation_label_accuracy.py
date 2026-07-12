#!/usr/bin/env python3
"""Compute per-tab label accuracy for the validation workbook.

Rows with no corrected value are treated as accepted/correct labels. Rows with a
corrected value are treated as reviewed changes and are correct only when the
corrected value matches the predicted label. By default, all rows are included.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS}

TABLE_FIELDS = (
    "is_integration_test",
    "data_load_location",
    "data_load_mechanism",
    "data_load_mechanism_is_required",
    "data_cleanup_location",
    "data_cleanup_mechanism",
    "data_cleanup_mechanism_is_required",
)

TABLE_HEADERS = (
    "Application",
    "Integration",
    "DL Location",
    "DL Mechanism",
    "DL Required",
    "DC Location",
    "DC Mechanism",
    "DC Required",
)


@dataclass
class LabelStats:
    evaluated: int = 0
    correct: int = 0
    incorrect: int = 0
    corrected: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.evaluated if self.evaluated else 0.0


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


def is_true(value: object) -> bool:
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def discover_label_fields(header: list[str]) -> list[str]:
    fields: list[str] = []
    columns = set(header)
    for column in header:
        if not column.startswith("label; "):
            continue

        field = column[len("label; ") :]
        corrected_column = f"review; {field}; corrected_value"
        if corrected_column in columns:
            fields.append(field)
    return fields


def analyze_workbook(
    workbook_path: Path,
    *,
    integration_only: bool,
) -> tuple[dict[str, dict[str, LabelStats]], dict[str, LabelStats]]:
    by_tab: dict[str, dict[str, LabelStats]] = {}
    overall: dict[str, LabelStats] = defaultdict(LabelStats)

    with ZipFile(workbook_path) as workbook:
        shared_strings = read_shared_strings(workbook)
        for tab_name, sheet_path in sheet_paths(workbook):
            rows = iter(read_sheet_rows(workbook, sheet_path, shared_strings))
            try:
                header = next(rows)
            except StopIteration:
                by_tab[tab_name] = {}
                continue

            indexes = {name: index for index, name in enumerate(header)}
            fields = discover_label_fields(header)
            by_tab[tab_name] = {field: LabelStats() for field in fields}

            if integration_only and "is_integration_test" not in fields:
                raise ValueError(
                    f"{tab_name}: missing label/review columns for is_integration_test"
                )

            for row in rows:
                if integration_only and not is_true(
                    final_value(row, indexes, "is_integration_test")
                ):
                    continue

                for field in fields:
                    predicted = cell(row, indexes, f"label; {field}")
                    corrected = cell(row, indexes, f"review; {field}; corrected_value")
                    if not predicted and not corrected:
                        continue

                    is_correct = not corrected or predicted == corrected
                    tab_stats = by_tab[tab_name][field]
                    overall_stats = overall[field]

                    tab_stats.evaluated += 1
                    overall_stats.evaluated += 1
                    if is_correct:
                        tab_stats.correct += 1
                        overall_stats.correct += 1
                    else:
                        tab_stats.incorrect += 1
                        tab_stats.corrected += 1
                        overall_stats.incorrect += 1
                        overall_stats.corrected += 1

    return by_tab, dict(overall)


def format_percent(stats: LabelStats) -> str:
    if not stats.evaluated:
        return "N/A"
    return f"{stats.accuracy * 100:.2f}%"


def build_stdout_table(
    by_tab: dict[str, dict[str, LabelStats]],
    overall: dict[str, LabelStats],
) -> str:
    rows: list[list[str]] = []
    for tab_name, label_stats in by_tab.items():
        rows.append(
            [tab_name]
            + [format_percent(label_stats.get(field, LabelStats())) for field in TABLE_FIELDS]
        )

    overall_row = ["Overall"] + [
        format_percent(overall.get(field, LabelStats())) for field in TABLE_FIELDS
    ]

    widths = [
        max(len(row[index]) for row in ([list(TABLE_HEADERS)] + rows + [overall_row]))
        for index in range(len(TABLE_HEADERS))
    ]

    def render_row(row: list[str]) -> str:
        cells = [row[0].ljust(widths[0])]
        cells.extend(value.rjust(width) for value, width in zip(row[1:], widths[1:]))
        return "  ".join(cells)

    header = render_row(list(TABLE_HEADERS))
    divider = "-" * len(header)
    lines = [
        "TABLE: Labeling accuracy of ATLAS",
        divider,
        header,
        divider,
    ]
    lines.extend(render_row(row) for row in rows)
    lines.append(divider)
    lines.append(render_row(overall_row))
    return "\n".join(lines)


def write_accuracy_csv(
    output_path: Path,
    by_tab: dict[str, dict[str, LabelStats]],
    overall: dict[str, LabelStats],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "tab",
                "label",
                "evaluated",
                "correct",
                "incorrect",
                "corrected",
                "accuracy",
            ),
        )
        writer.writeheader()

        for label in sorted(overall):
            stats = overall[label]
            writer.writerow(format_row("ALL", label, stats))

        for tab_name, label_stats in by_tab.items():
            for label in label_stats:
                writer.writerow(format_row(tab_name, label, label_stats[label]))


def format_row(tab: str, label: str, stats: LabelStats) -> dict[str, str | int]:
    return {
        "tab": tab,
        "label": label,
        "evaluated": stats.evaluated,
        "correct": stats.correct,
        "incorrect": stats.incorrect,
        "corrected": stats.corrected,
        "accuracy": f"{stats.accuracy:.4f}" if stats.evaluated else "",
    }


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    default_results_dir = script_path.parents[1]

    parser = argparse.ArgumentParser(
        description=(
            "Compute accuracy for every label/review correction pair on every "
            "tab in results/validation_dataset.xlsx."
        )
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=default_results_dir / "validation_dataset.xlsx",
        help="Path to the validation workbook.",
    )
    row_scope = parser.add_mutually_exclusive_group()
    row_scope.add_argument(
        "--integration-only",
        dest="integration_only",
        action="store_true",
        help="Only include rows whose final is_integration_test value is true.",
    )
    row_scope.add_argument(
        "--all-rows",
        dest="integration_only",
        action="store_false",
        default=False,
        help="Include all rows, regardless of final is_integration_test value. This is the default.",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        help="Optional CSV path for per-tab label accuracy results.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    by_tab, overall = analyze_workbook(
        args.workbook,
        integration_only=args.integration_only,
    )

    print(build_stdout_table(by_tab, overall))

    if args.csv_output:
        write_accuracy_csv(args.csv_output, by_tab, overall)
        print(f"\nCSV output: {args.csv_output}")


if __name__ == "__main__":
    main()
