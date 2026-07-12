#!/usr/bin/env python3
"""Generate RQ3 load-to-cleanup alluvial diagrams from full-dataset JSON labels."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from patterns_alluvial import (
    GROUPS,
    is_true,
    normalize,
    plot_alluvial,
    remap_small_categories,
    write_pair_counts,
)


def final_label_for(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    final_label = value.get("final_label")
    if isinstance(final_label, dict):
        return final_label
    return None


def read_json_pattern_pairs(
    labels_dir: Path,
    *,
    integration_only: bool,
    include_blank: bool,
) -> tuple[dict[str, Counter[tuple[str, str]]], int, int]:
    pairs_by_group = {group_name: Counter() for group_name in GROUPS}
    included_records = 0
    skipped_records = 0

    for json_path in sorted(labels_dir.glob("*.json"), key=lambda path: path.stem.lower()):
        with json_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"{json_path} must contain a JSON object")

        for record in payload.values():
            final_label = final_label_for(record)
            if final_label is None:
                skipped_records += 1
                continue

            if integration_only and not is_true(final_label.get("is_integration_test")):
                continue

            record_included = False
            for group_name, fields in GROUPS.items():
                load_value = normalize(final_label.get(fields[0]))
                cleanup_value = normalize(final_label.get(fields[1]))
                if not load_value:
                    if not include_blank:
                        continue
                    load_value = "(blank)"
                if not cleanup_value:
                    if not include_blank:
                        continue
                    cleanup_value = "(blank)"

                pairs_by_group[group_name][(load_value, cleanup_value)] += 1
                record_included = True

            if record_included:
                included_records += 1

    return pairs_by_group, included_records, skipped_records


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    results_dir = script_path.parents[2]

    parser = argparse.ArgumentParser(
        description=(
            "Read full-dataset JSON labeling results and generate load-to-cleanup "
            "alluvial diagrams for locations and mechanisms."
        )
    )
    parser.add_argument(
        "--labels-dir",
        type=Path,
        default=results_dir / "labels_full_dataset",
        help="Directory containing per-project JSON label files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=results_dir / "RQ3" / "full_dataset_alluvial",
        help="Output directory for figures and pair-count CSV.",
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
    parser.add_argument(
        "--include-blank",
        action="store_true",
        help="Include blank/unlabeled values as a '(blank)' category.",
    )
    parser.add_argument(
        "--location-min-percent",
        type=float,
        default=0.0,
        help="Group location side categories below this percentage into Other (default: 0.0).",
    )
    parser.add_argument(
        "--mechanism-min-percent",
        type=float,
        default=1.0,
        help="Group mechanism side categories below this percentage into Other (default: 1.0).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.labels_dir.exists():
        raise FileNotFoundError(f"Labels directory not found: {args.labels_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    pairs_by_group, included_records, skipped_records = read_json_pattern_pairs(
        args.labels_dir,
        integration_only=args.integration_only,
        include_blank=args.include_blank,
    )

    generated = []
    csv_rows: list[dict[str, object]] = []
    min_percent_by_group = {
        "location": args.location_min_percent,
        "mechanism": args.mechanism_min_percent,
    }
    for group_name, pairs in pairs_by_group.items():
        min_percent = min_percent_by_group[group_name]
        generated.append(
            plot_alluvial(
                pairs,
                group_name=group_name,
                output_dir=args.output_dir,
                min_percent=min_percent,
            )
        )

        remapped = remap_small_categories(pairs, min_percent=min_percent)
        for (load_category, cleanup_category), count in remapped.most_common():
            csv_rows.append(
                {
                    "group": group_name,
                    "load_category": load_category,
                    "cleanup_category": cleanup_category,
                    "count": count,
                }
            )

    summary_csv = args.output_dir / "load_to_cleanup_pair_counts.csv"
    write_pair_counts(summary_csv, csv_rows)

    print(f"Applications analyzed: {len(list(args.labels_dir.glob('*.json')))}")
    print(f"Records included: {included_records}")
    print(f"Records skipped without final_label: {skipped_records}")
    print(f"Pair-count CSV: {summary_csv}")
    print("Figures:")
    for path in generated:
        print(f"  {path}")


if __name__ == "__main__":
    main()
