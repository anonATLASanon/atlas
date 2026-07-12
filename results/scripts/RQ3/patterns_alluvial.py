#!/usr/bin/env python3
"""Generate RQ3 load-to-cleanup alluvial diagrams from validation xlsx labels."""

from __future__ import annotations

import argparse
import csv
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile


os.environ.setdefault("MPLCONFIGDIR", str(Path("/tmp") / "matplotlib-cache"))

import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Rectangle


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS}

GROUPS = {
    "location": ("data_load_location", "data_cleanup_location"),
    "mechanism": ("data_load_mechanism", "data_cleanup_mechanism"),
}

STACK_COLORS = (
    "#4E79A7",
    "#F28E2B",
    "#59A14F",
    "#76B7B2",
    "#EDC948",
    "#E15759",
    "#B07AA1",
    "#BAB0AC",
    "#FF9DA7",
    "#9C755F",
    "#2F4B7C",
    "#A05195",
)

DISPLAY_NAMES = {
    "test_fixture_method": "Test fixture method",
    "test_method": "Test method",
    "test_annotation": "Test annotation",
    "not_present": "Not present",
    "not_needed": "Not needed",
    "persistence_framework_api_call": "Persistence framework API",
    "mocking_stubbing_api_call": "Mocking/stubbing API",
    "framework_annotation": "Framework annotation",
    "file_system_resource_api_call": "File-system resource API",
    "rest_http_api_call": "REST/HTTP API",
    "other_java_api_call": "Other Java API",
    "in_memory_server_setup": "In-memory server setup",
    "does_not_fit_with_any_pattern": "Does not fit any pattern",
    "custom_protocol_api_call": "Custom protocol API",
    "process_management_api_call": "Process management API",
    "(blank)": "(blank)",
    "Other": " All Other Categories",
}


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


def display_name(category: str) -> str:
    return DISPLAY_NAMES.get(category, category)


def save_figure(fig: plt.Figure, outdir: Path, stem: str) -> None:
    for extension in ("png", "pdf", "svg"):
        kwargs = {"bbox_inches": "tight"}
        if extension == "png":
            kwargs["dpi"] = 300
        fig.savefig(outdir / f"{stem}.{extension}", **kwargs)
    plt.close(fig)


def required_columns(fields: tuple[str, str]) -> set[str]:
    columns = {"label; is_integration_test", "review; is_integration_test; corrected_value"}
    for field in fields:
        columns.add(f"label; {field}")
        columns.add(f"review; {field}; corrected_value")
    return columns


def iter_pattern_pairs(
    workbook_path: Path,
    fields: tuple[str, str],
    *,
    integration_only: bool,
    include_blank: bool,
) -> Iterable[tuple[str, str]]:
    with ZipFile(workbook_path) as workbook:
        shared_strings = read_shared_strings(workbook)
        for app_name, sheet_path in sheet_paths(workbook):
            rows = iter(read_sheet_rows(workbook, sheet_path, shared_strings))
            try:
                header = next(rows)
            except StopIteration:
                continue

            missing = sorted(required_columns(fields) - set(header))
            if missing:
                raise ValueError(f"{app_name}: missing required columns: {', '.join(missing)}")

            header_indexes = {name: index for index, name in enumerate(header)}
            for row in rows:
                if integration_only and not is_true(
                    final_value(row, header_indexes, "is_integration_test")
                ):
                    continue

                load_value = normalize(final_value(row, header_indexes, fields[0]))
                cleanup_value = normalize(final_value(row, header_indexes, fields[1]))
                if not load_value:
                    if not include_blank:
                        continue
                    load_value = "(blank)"
                if not cleanup_value:
                    if not include_blank:
                        continue
                    cleanup_value = "(blank)"
                yield load_value, cleanup_value


def remap_small_categories(
    pairs: Counter[tuple[str, str]],
    *,
    min_percent: float,
) -> Counter[tuple[str, str]]:
    total = sum(pairs.values())
    if total == 0:
        return pairs

    left_totals: Counter[str] = Counter()
    right_totals: Counter[str] = Counter()
    for (left, right), count in pairs.items():
        left_totals[left] += count
        right_totals[right] += count

    def mapped(category: str, totals: Counter[str]) -> str:
        percent = totals[category] / total * 100
        if percent < min_percent:
            return "Other"
        return category

    remapped: Counter[tuple[str, str]] = Counter()
    for (left, right), count in pairs.items():
        remapped[(mapped(left, left_totals), mapped(right, right_totals))] += count
    return remapped


def side_totals(pairs: Counter[tuple[str, str]]) -> tuple[Counter[str], Counter[str]]:
    left_totals: Counter[str] = Counter()
    right_totals: Counter[str] = Counter()
    for (left, right), count in pairs.items():
        left_totals[left] += count
        right_totals[right] += count
    return left_totals, right_totals


def ordered_categories(totals: Counter[str]) -> list[str]:
    return [category for category, _ in totals.most_common()]


def category_colors(
    left_categories: list[str],
    right_categories: list[str],
    left_totals: Counter[str],
    right_totals: Counter[str],
) -> dict[str, str]:
    combined = Counter(left_totals)
    combined.update(right_totals)
    categories = sorted(
        set(left_categories) | set(right_categories),
        key=lambda category: (-combined[category], display_name(category)),
    )
    return {
        category: STACK_COLORS[index % len(STACK_COLORS)]
        for index, category in enumerate(categories)
    }


def layout_nodes(
    categories: list[str],
    totals: Counter[str],
    *,
    scale: float,
    center: float,
    gap: float,
) -> dict[str, tuple[float, float]]:
    total_height = (
        sum(totals[category] * scale for category in categories)
        + gap * max(0, len(categories) - 1)
    )
    y_top = center + total_height / 2
    y = y_top
    nodes: dict[str, tuple[float, float]] = {}
    for category in categories:
        height = totals[category] * scale
        nodes[category] = (y - height, y)
        y -= height + gap
    return nodes


def add_flow(
    ax: plt.Axes,
    *,
    x0: float,
    x1: float,
    y0_low: float,
    y0_high: float,
    y1_low: float,
    y1_high: float,
    color: str,
) -> None:
    curve = 0.42 * (x1 - x0)
    path = MplPath(
        [
            (x0, y0_high),
            (x0 + curve, y0_high),
            (x1 - curve, y1_high),
            (x1, y1_high),
            (x1, y1_low),
            (x1 - curve, y1_low),
            (x0 + curve, y0_low),
            (x0, y0_low),
            (x0, y0_high),
        ],
        [
            MplPath.MOVETO,
            MplPath.CURVE4,
            MplPath.CURVE4,
            MplPath.CURVE4,
            MplPath.LINETO,
            MplPath.CURVE4,
            MplPath.CURVE4,
            MplPath.CURVE4,
            MplPath.CLOSEPOLY,
        ],
    )
    ax.add_patch(PathPatch(path, facecolor=color, edgecolor="none", alpha=0.42))


def add_node(
    ax: plt.Axes,
    *,
    x: float,
    y_low: float,
    y_high: float,
    color: str,
    width: float,
) -> None:
    ax.add_patch(
        Rectangle(
            (x - width / 2, y_low),
            width,
            y_high - y_low,
            facecolor=color,
            edgecolor="white",
            linewidth=0.8,
            zorder=5,
        )
    )


def annotate_side(
    ax: plt.Axes,
    *,
    categories: list[str],
    totals: Counter[str],
    nodes: dict[str, tuple[float, float]],
    x: float,
    align: str,
    side: str,
    node_x: float,
    node_width: float,
    total: int,
) -> None:
    for category in categories:
        y_low, y_high = nodes[category]
        count = totals[category]
        percent = count / total * 100 if total else 0
        y_mid = (y_low + y_high) / 2
        label = f"{display_name(category)}\n{percent:.1f}% ({count})"
        if side == "left":
            estimated_label_width = min(0.21, 0.0037 * len(label))
            line_start = min(node_x - node_width / 2 - 0.008, x + estimated_label_width + 0.006)
            line_end = node_x - node_width / 2
        else:
            line_start = node_x + node_width / 2
            line_end = x - 0.015
        ax.plot(
            [line_start, line_end],
            [y_mid, y_mid],
            color="#9a9a9a",
            linewidth=0.7,
            alpha=0.8,
            zorder=4,
        )
        ax.text(
            x,
            y_mid,
            label,
            ha=align,
            va="center",
            fontsize=7,
            color="black",
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6},
            zorder=7,
        )


def plot_alluvial(
    pairs: Counter[tuple[str, str]],
    *,
    group_name: str,
    output_dir: Path,
    min_percent: float,
) -> Path:
    pairs = remap_small_categories(pairs, min_percent=min_percent)
    total = sum(pairs.values())
    left_totals, right_totals = side_totals(pairs)
    left_categories = ordered_categories(left_totals)
    right_categories = ordered_categories(right_totals)
    color_by_category = category_colors(
        left_categories,
        right_categories,
        left_totals,
        right_totals,
    )

    node_gap = 0.05
    max_side_categories = max(len(left_categories), len(right_categories))
    max_stack_height = 0.82
    scale = (
        (max_stack_height - node_gap * max(0, max_side_categories - 1)) / total
        if total
        else 0
    )
    left_nodes = layout_nodes(
        left_categories,
        left_totals,
        scale=scale,
        center=0.515,
        gap=node_gap,
    )
    right_nodes = layout_nodes(
        right_categories,
        right_totals,
        scale=scale,
        center=0.515,
        gap=node_gap,
    )

    left_offsets = defaultdict(float)
    right_offsets = defaultdict(float)

    fig, ax = plt.subplots(figsize=(11.2, 5.2))
    ax.set_xlim(0.035, 0.86)
    ax.set_ylim(0, 1)
    ax.axis("off")

    x_left = 0.31
    x_right = 0.67
    left_label_x = 0.075
    right_label_x = 0.705
    node_width = 0.03

    for left in left_categories:
        for right in right_categories:
            count = pairs.get((left, right), 0)
            if not count:
                continue

            flow_height = count * scale
            left_low = left_nodes[left][1] - left_offsets[left] - flow_height
            left_high = left_nodes[left][1] - left_offsets[left]
            right_low = right_nodes[right][1] - right_offsets[right] - flow_height
            right_high = right_nodes[right][1] - right_offsets[right]
            left_offsets[left] += flow_height
            right_offsets[right] += flow_height
            add_flow(
                ax,
                x0=x_left,
                x1=x_right,
                y0_low=left_low,
                y0_high=left_high,
                y1_low=right_low,
                y1_high=right_high,
                color=color_by_category[left],
            )

    for category in left_categories:
        add_node(
            ax,
            x=x_left,
            y_low=left_nodes[category][0],
            y_high=left_nodes[category][1],
            color=color_by_category[category],
            width=node_width,
        )
    for category in right_categories:
        add_node(
            ax,
            x=x_right,
            y_low=right_nodes[category][0],
            y_high=right_nodes[category][1],
            color=color_by_category[category],
            width=node_width,
        )

    title = "mechanism" if group_name == "mechanism" else "location"
    ax.text(left_label_x, 0.985, f"Load {title}\n(total: {total})", ha="left", va="top", fontsize=10)
    ax.text(right_label_x, 0.985, f"Cleanup {title}\n(total: {total})", ha="left", va="top", fontsize=10)

    annotate_side(
        ax,
        categories=left_categories,
        totals=left_totals,
        nodes=left_nodes,
        x=left_label_x,
        align="left",
        side="left",
        node_x=x_left,
        node_width=node_width,
        total=total,
    )
    annotate_side(
        ax,
        categories=right_categories,
        totals=right_totals,
        nodes=right_nodes,
        x=right_label_x,
        align="left",
        side="right",
        node_x=x_right,
        node_width=node_width,
        total=total,
    )

    ax.text(
        0.5,
        0.02,
        "Flow width proportional to number of tests",
        ha="center",
        va="bottom",
        fontsize=9,
    )

    output_stem = f"{group_name}_load_to_cleanup_alluvial"
    save_figure(fig, output_dir, output_stem)
    return output_dir / f"{output_stem}.png"


def write_pair_counts(output_path: Path, rows: list[dict[str, object]]) -> None:
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("group", "load_category", "cleanup_category", "count"),
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    results_dir = script_path.parents[2]
    parser = argparse.ArgumentParser(
        description="Generate load-to-cleanup alluvial diagrams from validation xlsx labels."
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
        default=results_dir / "RQ3" / "alluvial",
        help="Output directory for figures and pair-count CSV.",
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
    parser.add_argument(
        "--min-percent",
        type=float,
        default=3.0,
        help="Group side categories below this percentage into Other (default: 3.0).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    generated = []
    csv_rows: list[dict[str, object]] = []
    for group_name, fields in GROUPS.items():
        pairs = Counter(
            iter_pattern_pairs(
                args.workbook,
                fields,
                integration_only=args.integration_only,
                include_blank=args.include_blank,
            )
        )
        generated.append(
            plot_alluvial(
                pairs,
                group_name=group_name,
                output_dir=args.outdir,
                min_percent=args.min_percent,
            )
        )

        remapped = remap_small_categories(pairs, min_percent=args.min_percent)
        for (load_category, cleanup_category), count in remapped.most_common():
            csv_rows.append(
                {
                    "group": group_name,
                    "load_category": load_category,
                    "cleanup_category": cleanup_category,
                    "count": count,
                }
            )

    summary_csv = args.outdir / "load_to_cleanup_pair_counts.csv"
    write_pair_counts(summary_csv, csv_rows)

    print(f"Pair-count CSV: {summary_csv}")
    print("Figures:")
    for path in generated:
        print(f"  {path}")


if __name__ == "__main__":
    main()
