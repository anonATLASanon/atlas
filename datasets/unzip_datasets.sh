#!/usr/bin/env bash
set -euo pipefail

datasets_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

unzip_dataset() {
  local archive="$1"
  local target="$2"

  mkdir -p "$target"
  unzip -o "$archive" -d "$target"
}

unzip_dataset "$datasets_dir/agent-generated.zip" "$datasets_dir/agent-generated"
unzip_dataset "$datasets_dir/full.zip" "$datasets_dir/full"
unzip_dataset "$datasets_dir/validation.zip" "$datasets_dir/validation"
