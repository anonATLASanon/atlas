#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
agent_generated_dir="${AGENT_GENERATED_DIR:-$repo_root/datasets/agent-generated}"
output_dir="${OUTPUT_DIR:-$repo_root/results/atlas_agent_generated_runs}"

config_path="$repo_root/src/coaster_label/config/coaster_config.py"
analysis_provider="$repo_root/src/coaster_label/config/cldk_analysis_provider.py"
analysis_timeout="${ANALYSIS_TIMEOUT:-600}"

if [[ ! -d "$agent_generated_dir" ]]; then
  echo "Agent-generated dataset directory not found: $agent_generated_dir" >&2
  exit 1
fi

mkdir -p "$output_dir"

for project_path in "$agent_generated_dir"/*; do
  [[ -d "$project_path" ]] || continue

  app_name="$(basename "$project_path")"

  echo "Running Atlas on $app_name"
  angelica label-units \
    --config "$config_path" \
    --project-path "$project_path" \
    --analysis-provider "$analysis_provider" \
    --db "$output_dir/$app_name.labels.db" \
    --index-dir "$output_dir/$app_name.vector_index" \
    --clear-cache \
    --analysis-timeout "$analysis_timeout" \
    --out "$output_dir/$app_name.json"
done
