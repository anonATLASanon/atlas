#!/usr/bin/env python3
"""Generate RQ3 grouped heatmaps from the validation xlsx workbook."""

from __future__ import annotations

import argparse
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile


os.environ.setdefault("MPLCONFIGDIR", str(Path("/tmp") / "matplotlib-cache"))

import matplotlib.pyplot as plt
import numpy as np


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS}

FIGURE_GROUPS = {
    "locations": ("data_load_location", "data_cleanup_location"),
    "mechanisms": ("data_load_mechanism", "data_cleanup_mechanism"),
}

APPLICATION_ORDER = [
    "catwatch",
    "cwa-verification",
    "features-service",
    "genome-nexus",
    "gestaohospital",
    "languagetool",
    "market",
    "ocvn",
    "proxyprint",
    "ofbiz",
    "petclinic",
    "shopizer",
]

LOCATION_CATEGORIES = [
    "test_fixture_method",
    "test_method",
    "test_annotation",
    "not_present",
]

MECHANISM_CATEGORIES = [
    "persistence_framework_api_call",
    "not_needed",
    "mocking_stubbing_api_call",
    "framework_annotation",
    "file_system_resource_api_call",
    "rest_http_api_call",
    "not_present",
    "other_java_api_call",
    "in_memory_server_setup",
    "does_not_fit_with_any_pattern",
    "custom_protocol_api_call",
    "process_management_api_call",
    "other",
]

DISPLAY_NAMES = {
    "test_fixture_method": "Test fixture method",
    "test_method": "Test method",
    "test_annotation": "Test annotation",
    "not_present": "Not present",
    "persistence_framework_api_call": "Persistence framework API",
    "not_needed": "Not needed",
    "mocking_stubbing_api_call": "Mocking/stubbing API",
    "framework_annotation": "Framework annotation",
    "file_system_resource_api_call": "File-system resource API",
    "rest_http_api_call": "REST/HTTP API",
    "other_java_api_call": "Other Java API",
    "in_memory_server_setup": "In-memory server setup",
    "does_not_fit_with_any_pattern": "Does not fit any pattern",
    "custom_protocol_api_call": "Custom protocol API",
    "process_management_api_call": "Process management API",
    "other": "Other",
}

BLUE_LIGHT = "#dbeafe"
GREEN_LIGHT = "#dcfce7"
GRID_COLOR = "#d9e3f0"
TEXT_DARK = "#1a1a1a"

plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#444444",
        "axes.labelcolor": "#222222",
        "xtick.color": "#222222",
        "ytick.color": "#222222",
        "font.size": 11,
        "axes.titleweight": "bold",
    }
)


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


def read_pattern_counts(
    workbook_path: Path,
    *,
    integration_only: bool,
    include_blank: bool,
) -> tuple[dict[str, dict[str, Counter[str]]], dict[str, int]]:
    fields = tuple(field for group_fields in FIGURE_GROUPS.values() for field in group_fields)
    counts: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: {field: Counter() for field in fields}
    )
    row_counts: dict[str, int] = Counter()
    required_columns = {
        column
        for field in (*fields, "is_integration_test")
        for column in (f"label; {field}", f"review; {field}; corrected_value")
    }

    with ZipFile(workbook_path) as workbook:
        shared_strings = read_shared_strings(workbook)
        for application, sheet_path in sheet_paths(workbook):
            counts[application]
            rows = iter(read_sheet_rows(workbook, sheet_path, shared_strings))
            try:
                header = next(rows)
            except StopIteration:
                continue

            missing = sorted(required_columns - set(header))
            if missing:
                raise ValueError(f"{application}: missing required columns: {', '.join(missing)}")

            indexes = {name: index for index, name in enumerate(header)}
            for row in rows:
                if integration_only and not is_true(
                    final_value(row, indexes, "is_integration_test")
                ):
                    continue

                row_has_pattern = False
                for field in fields:
                    value = final_value(row, indexes, field)
                    if not value:
                        if not include_blank:
                            continue
                        value = "(blank)"
                    counts[application][field][value] += 1
                    row_has_pattern = True

                if row_has_pattern:
                    row_counts[application] += 1

    return dict(counts), dict(row_counts)


def label(category: str) -> str:
    return DISPLAY_NAMES.get(category, category.replace("_", " ").title())


def application_label(application: str) -> str:
    if application == "cwa-verification-server":
        return "cwa-verification"
    return application


def application_sort_key(application: str) -> tuple[int, str]:
    display_label = application_label(application)
    try:
        return APPLICATION_ORDER.index(display_label), display_label
    except ValueError:
        return len(APPLICATION_ORDER), display_label


def validate(rows: list[dict[str, object]]) -> None:
    required = {
        "application",
        "group",
        "field",
        "category",
        "count",
        "rows_included",
    }
    for row in rows:
        missing = required.difference(row)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")
        if int(row["rows_included"]) <= 0:
            raise ValueError("rows_included must be positive.")
        if int(row["count"]) < 0:
            raise ValueError("count cannot be negative.")


def dataframe_from_workbook(
    workbook: Path,
    *,
    integration_only: bool,
    include_blank: bool,
) -> list[dict[str, object]]:
    counts, row_counts = read_pattern_counts(
        workbook,
        integration_only=integration_only,
        include_blank=include_blank,
    )

    rows = []
    for application, app_counts in counts.items():
        rows_included = row_counts.get(application, 0)
        for group, fields in FIGURE_GROUPS.items():
            for field in fields:
                for category, count in app_counts[field].items():
                    rows.append(
                        {
                            "application": application,
                            "group": group,
                            "field": field,
                            "category": category,
                            "count": count,
                            "rows_included": rows_included,
                        }
                    )

    return rows


def save_figure(fig: plt.Figure, outdir: Path, stem: str) -> None:
    for extension in ("png", "pdf", "svg"):
        kwargs = {"bbox_inches": "tight"}
        if extension == "png":
            kwargs["dpi"] = 300
        fig.savefig(outdir / f"{stem}.{extension}", **kwargs)
    plt.close(fig)


def add_phase_header(ax: plt.Axes, text: str, facecolor: str) -> None:
    ax.add_patch(
        plt.Rectangle(
            (0, 1.015),
            1,
            0.075,
            transform=ax.transAxes,
            facecolor=facecolor,
            edgecolor="black",
            linewidth=1.0,
            clip_on=False,
            zorder=5,
        )
    )
    ax.text(
        0.5,
        1.052,
        text,
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=13,
        fontweight="bold",
        color="black",
        clip_on=False,
        zorder=6,
    )


def make_grouped_heatmap(
    rows: list[dict[str, object]],
    *,
    group: str,
    load_field: str,
    cleanup_field: str,
    categories: list[str],
    output_stem: str,
    outdir: Path,
    width: float,
    layout: str,
) -> None:
    applications = sorted(
        {str(row["application"]) for row in rows},
        key=application_sort_key,
    )
    application_labels = [application_label(application) for application in applications]
    percentages: dict[tuple[str, str, str], float] = defaultdict(float)
    for row in rows:
        if row["group"] != group:
            continue
        percentages[
            (
                str(row["application"]),
                str(row["field"]),
                str(row["category"]),
            )
        ] += float(row["percentage"])

    xlabels = [label(category) for category in categories]
    matrices = []
    for field in (load_field, cleanup_field):
        matrices.append(
            np.column_stack(
                [
                    np.array(
                        [
                            percentages.get((application, field, category), 0.0)
                            for application in applications
                        ]
                    )
                    for category in categories
                ]
            )
        )

    if layout == "horizontal":
        height = max(5.5, 0.55 * len(applications) + 2.2)
        fig, axes = plt.subplots(
            nrows=1,
            ncols=2,
            figsize=(width, height),
            sharey=True,
            constrained_layout=True,
        )
    elif layout == "vertical":
        height = max(8.5, 0.95 * len(applications) + 3.0)
        fig, axes = plt.subplots(
            nrows=2,
            ncols=1,
            figsize=(width, height),
            sharex=True,
            constrained_layout=True,
        )
    else:
        raise ValueError(f"Unknown heatmap layout: {layout}")

    images = []
    axes_array = np.asarray(axes).ravel()
    for index, (ax, matrix, phase_title, phase_box_color) in enumerate(
        zip(
            axes_array,
            matrices,
            ("Data Load", "Data Cleanup"),
            (BLUE_LIGHT, GREEN_LIGHT),
        )
    ):
        image = ax.imshow(matrix, aspect="auto", cmap="Blues", vmin=0, vmax=100)
        images.append(image)

        add_phase_header(ax, phase_title, phase_box_color)
        ax.set_ylabel("Application")
        ax.set_yticks(np.arange(len(applications)))
        ax.set_yticklabels(application_labels)
        if layout == "horizontal" and index > 0:
            ax.set_ylabel("")
            ax.tick_params(labelleft=False)

        ax.set_xticks(np.arange(-0.5, matrix.shape[1], 1), minor=True)
        ax.set_yticks(np.arange(-0.5, matrix.shape[0], 1), minor=True)
        ax.grid(which="minor", color=GRID_COLOR, linewidth=0.6)
        ax.tick_params(which="minor", bottom=False, left=False)

        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                value = matrix[row, column]
                if value > 0:
                    text_color = "white" if value >= 55 else TEXT_DARK
                    ax.text(
                        column,
                        row,
                        f"{value:.0f}",
                        ha="center",
                        va="center",
                        fontsize=9,
                        color=text_color,
                    )

    if layout == "horizontal":
        for ax in axes_array:
            ax.set_xlabel("Category")
            ax.set_xticks(np.arange(len(xlabels)))
            ax.set_xticklabels(xlabels, rotation=45, ha="right")
    else:
        axes_array[-1].set_xlabel("Category")
        axes_array[-1].set_xticks(np.arange(len(xlabels)))
        axes_array[-1].set_xticklabels(xlabels, rotation=45, ha="right")

    colorbar = fig.colorbar(images[0], ax=axes_array, fraction=0.025, pad=0.02)
    colorbar.set_label("Percentage of tests within application (%)")
    save_figure(fig, outdir, output_stem)


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    results_dir = script_path.parents[2]
    parser = argparse.ArgumentParser(
        description="Generate grouped heatmaps for validation pattern distributions."
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=results_dir / "validation_dataset.xlsx",
        help="Input xlsx workbook.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=results_dir / "RQ3" / "heatmaps",
        help="Output directory.",
    )
    parser.add_argument(
        "--integration-only",
        dest="integration_only",
        action="store_true",
        default=True,
        help="Only include rows whose final is_integration_test value is true. This is the default.",
    )
    parser.add_argument(
        "--all-tests",
        dest="integration_only",
        action="store_false",
        help="Include all rows, regardless of final is_integration_test value.",
    )
    parser.add_argument(
        "--include-blank",
        action="store_true",
        help="Include blank/unlabeled values as a '(blank)' category.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    rows = dataframe_from_workbook(
        args.workbook,
        integration_only=args.integration_only,
        include_blank=args.include_blank,
    )
    validate(rows)
    for row in rows:
        row["percentage"] = int(row["count"]) / int(row["rows_included"]) * 100

    make_grouped_heatmap(
        rows,
        group="locations",
        load_field="data_load_location",
        cleanup_field="data_cleanup_location",
        categories=LOCATION_CATEGORIES,
        output_stem="location_grouped_heatmap",
        outdir=args.outdir,
        width=10,
        layout="horizontal",
    )
    make_grouped_heatmap(
        rows,
        group="mechanisms",
        load_field="data_load_mechanism",
        cleanup_field="data_cleanup_mechanism",
        categories=MECHANISM_CATEGORIES,
        output_stem="mechanism_grouped_heatmap",
        outdir=args.outdir,
        width=12,
        layout="vertical",
    )

    print(f"Heatmaps written to: {args.outdir.resolve()}")


if __name__ == "__main__":
    main()
