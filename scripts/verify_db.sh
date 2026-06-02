#!/bin/sh
# verify_db.sh — standalone integrity + config report for the AXIOM SQLite DB.
#
# Runs PRAGMA integrity_check and PRAGMA quick_check, then reports the runtime
# PRAGMAs that P0-5 hardens (journal_mode, foreign_keys, busy_timeout, plus
# synchronous and wal_checkpoint state). Intended for the restore runbook and a
# periodic cron integrity check. Exits non-zero if either check is not "ok", so
# cron / CI can alert.
#
# Note: PRAGMA values reported here reflect THIS sqlite3 connection's defaults,
# not necessarily the live app's per-connection PRAGMAs (the app sets WAL,
# busy_timeout, foreign_keys at connect-time via P0-5). journal_mode and the WAL
# checkpoint state are persistent DB-file properties and are authoritative.
#
# Usage:
#   scripts/verify_db.sh [DB_PATH]
#
# Environment:
#   AXIOM_DB_PATH   Path to the SQLite DB to verify (default: /data/axiom.db)
#   SQLITE_BIN      sqlite3 binary                  (default: sqlite3)
#
# Exit codes: 0 both checks ok, 1 integrity_check failed, 2 quick_check failed,
#             3 usage/IO error.

set -eu

log() { printf '%s [verify_db] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
die() { log "ERROR: $*"; exit 3; }

DB_PATH="${1:-${AXIOM_DB_PATH:-/data/axiom.db}}"
SQLITE_BIN="${SQLITE_BIN:-sqlite3}"

command -v "$SQLITE_BIN" >/dev/null 2>&1 || die "sqlite3 binary '$SQLITE_BIN' not found in PATH"
[ -f "$DB_PATH" ] || die "DB not found at '$DB_PATH'"
[ -r "$DB_PATH" ] || die "DB not readable at '$DB_PATH'"

log "verifying '$DB_PATH'"

pragma() {
  # $1 = pragma expression; prints the scalar value (empty on error).
  "$SQLITE_BIN" "$DB_PATH" "PRAGMA $1;" 2>/dev/null || true
}

# --- Integrity checks -------------------------------------------------------
INTEGRITY="$("$SQLITE_BIN" "$DB_PATH" 'PRAGMA integrity_check;' 2>&1)" \
  || die "could not run integrity_check"
QUICK="$("$SQLITE_BIN" "$DB_PATH" 'PRAGMA quick_check;' 2>&1)" \
  || die "could not run quick_check"

# --- Config / runtime PRAGMA report ----------------------------------------
JOURNAL_MODE="$(pragma journal_mode)"
FOREIGN_KEYS="$(pragma foreign_keys)"
BUSY_TIMEOUT="$(pragma busy_timeout)"
SYNCHRONOUS="$(pragma synchronous)"
PAGE_SIZE="$(pragma page_size)"

printf '\n'
printf 'AXIOM DB verification report\n'
printf '  db_path        : %s\n' "$DB_PATH"
printf '  size_bytes     : %s\n' "$(wc -c <"$DB_PATH" | tr -d ' ')"
printf '  integrity_check: %s\n' "$INTEGRITY"
printf '  quick_check    : %s\n' "$QUICK"
printf '  journal_mode   : %s\n' "${JOURNAL_MODE:-<unknown>}"
printf '  foreign_keys   : %s\n' "${FOREIGN_KEYS:-<unknown>}"
printf '  busy_timeout   : %s\n' "${BUSY_TIMEOUT:-<unknown>}"
printf '  synchronous    : %s\n' "${SYNCHRONOUS:-<unknown>}"
printf '  page_size      : %s\n' "${PAGE_SIZE:-<unknown>}"
printf '\n'

# WAL hygiene note (only meaningful once P0-5 has put the DB into WAL mode).
if [ "$JOURNAL_MODE" = "wal" ]; then
  log "journal_mode=wal (P0-5 active); -wal/-shm sidecars are expected next to the DB"
else
  log "NOTE: journal_mode is '$JOURNAL_MODE', not 'wal'. P0-5 enables WAL at app connect-time."
fi

RC=0
if [ "$INTEGRITY" != "ok" ]; then
  log "integrity_check FAILED"
  RC=1
elif [ "$QUICK" != "ok" ]; then
  log "quick_check FAILED"
  RC=2
else
  log "OK: integrity_check and quick_check both passed"
fi

exit "$RC"
