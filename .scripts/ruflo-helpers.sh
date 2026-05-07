#!/usr/bin/env bash
# Ruflo helper functions for AXIOM-BRAIN dispatches.
#
# Background: ruflo v3.7.0-alpha.7 has a directory-walker bug — `ruflo analyze symbols src/`
# returns 0 files. Single-file invocation works correctly. These helpers wrap that
# constraint with TMPDIR isolation and a find+xargs walker.
#
# Source this file from CI scripts and dispatch shells:
#     source .scripts/ruflo-helpers.sh
#
# Then use:
#     ruflo_walk src/axiom symbols
#     ruflo_walk src/axiom/storage complexity
#     ruflo_lite analyze symbols src/axiom/storage/crud.py
#
# Note: ruflo_safe (with systemd-run cgroup) intentionally NOT included here. That
# wrapper strips env vars Ruflo's tree-sitter loader needs, breaking analyze. It's
# reserved for future hive-mind/swarm operations only, lives in ~/.bashrc.

# ruflo_lite — workhorse for analyze commands.
# TMPDIR isolation prevents EDQUOT crashes from temp-file accumulation across runs.
# 5-minute timeout caps any single-file analysis.
ruflo_lite() {
  local tmp_dir
  tmp_dir="$(mktemp -d -t ruflo.XXXXXX)"
  trap "rm -rf '$tmp_dir'" RETURN
  TMPDIR="$tmp_dir" timeout 300 ruflo "$@" 2>&1
}

# ruflo_walk — wraps find+xargs around ruflo_lite to fix alpha-7 directory bug.
# Default file pattern is *.py; pass a third arg to override (e.g. "*.ts").
#
# Usage:
#   ruflo_walk <target_dir> <subcmd>             # defaults to Python
#   ruflo_walk <target_dir> <subcmd> "*.ts"      # TypeScript
ruflo_walk() {
  local target_dir="$1"
  local subcmd="$2"
  local pattern="${3:-*.py}"
  if [ -z "$target_dir" ] || [ -z "$subcmd" ]; then
    echo "ruflo_walk: usage: ruflo_walk <dir> <subcmd> [pattern]" >&2
    return 2
  fi
  if [ ! -d "$target_dir" ]; then
    echo "ruflo_walk: directory not found: $target_dir" >&2
    return 1
  fi
  # Intentionally avoid xargs: it cannot execute shell functions portably.
  # This walker is safe in CI and any POSIX-ish environment with bash + find.
  while IFS= read -r -d '' f; do
    ruflo_lite analyze "$subcmd" "$f"
  done < <(find "$target_dir" -name "$pattern" -type f -print0)
}

# ruflo_walk_summary — short summary across many files.
# Aggregates "Total symbols" lines into a single count.
ruflo_walk_summary() {
  ruflo_walk "$@" | grep "Total symbols" | awk '{s+=$4} END{print "Aggregate symbols across files:", s}'
}

