#!/bin/sh
# backup_db.sh — safe online backup of the AXIOM SQLite DB (P1-7 / DB-004).
#
# Uses `sqlite3 <db> ".backup <dest>"`, which is WAL-safe and consistent even
# while the app is writing (it takes the SQLite backup API snapshot, not a raw
# file copy). The destination is timestamped, old backups are pruned to a
# retention count, and the freshly written backup is integrity-checked. If
# RCLONE_REMOTE is set, the backup is also copied offsite via rclone.
#
# Prerequisite: the DB runs in WAL mode (enabled by the P0-5 fix). The .backup
# API works regardless of journal mode, but WAL is what makes online backups of
# a live, actively-written DB reliable.
#
# Usage:
#   scripts/backup_db.sh [DB_PATH] [BACKUP_DIR]
#
# Environment (all optional, args override env where both apply):
#   AXIOM_DB_PATH     Path to the live SQLite DB        (default: /data/axiom.db)
#   AXIOM_BACKUP_DIR  Directory for backup files         (default: /backups)
#   BACKUP_RETENTION  Number of backups to keep          (default: 14)
#   RCLONE_REMOTE     rclone remote:path for offsite copy (default: unset)
#   SQLITE_BIN        sqlite3 binary                      (default: sqlite3)
#
# Exit codes: 0 ok, non-zero on any failure (fails loudly, never silently).

set -eu

log() { printf '%s [backup_db] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

DB_PATH="${1:-${AXIOM_DB_PATH:-/data/axiom.db}}"
BACKUP_DIR="${2:-${AXIOM_BACKUP_DIR:-/backups}}"
RETENTION="${BACKUP_RETENTION:-14}"
SQLITE_BIN="${SQLITE_BIN:-sqlite3}"

command -v "$SQLITE_BIN" >/dev/null 2>&1 || die "sqlite3 binary '$SQLITE_BIN' not found in PATH"

case "$RETENTION" in
  '' | *[!0-9]*) die "BACKUP_RETENTION must be a non-negative integer, got '$RETENTION'" ;;
esac
[ "$RETENTION" -ge 1 ] || die "BACKUP_RETENTION must be >= 1, got '$RETENTION'"

[ -f "$DB_PATH" ] || die "DB not found at '$DB_PATH'"
[ -r "$DB_PATH" ] || die "DB not readable at '$DB_PATH'"

mkdir -p "$BACKUP_DIR" || die "cannot create backup dir '$BACKUP_DIR'"
[ -w "$BACKUP_DIR" ] || die "backup dir '$BACKUP_DIR' is not writable"

TIMESTAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
DB_BASE="$(basename "$DB_PATH")"
DEST="${BACKUP_DIR}/${DB_BASE}.${TIMESTAMP}.bak"
DEST_TMP="${DEST}.partial"

log "backing up '$DB_PATH' -> '$DEST'"

# .backup uses the SQLite online backup API: a consistent snapshot across WAL.
# Write to a .partial file first so a crash never leaves a truncated .bak that
# retention would treat as a real backup.
if ! "$SQLITE_BIN" "$DB_PATH" ".backup '$DEST_TMP'"; then
  rm -f "$DEST_TMP"
  die "sqlite3 .backup failed for '$DB_PATH'"
fi

# Verify the backup is a valid, uncorrupted SQLite database before promoting it.
CHECK="$("$SQLITE_BIN" "$DEST_TMP" 'PRAGMA integrity_check;' 2>&1)" || {
  rm -f "$DEST_TMP"
  die "integrity_check could not run on backup: $CHECK"
}
if [ "$CHECK" != "ok" ]; then
  rm -f "$DEST_TMP"
  die "integrity_check FAILED on backup '$DEST_TMP': $CHECK"
fi
log "integrity_check ok"

mv "$DEST_TMP" "$DEST" || { rm -f "$DEST_TMP"; die "could not finalize backup '$DEST'"; }
BACKUP_SIZE="$(wc -c <"$DEST" | tr -d ' ')"
log "backup complete: $DEST (${BACKUP_SIZE} bytes)"

# Retention: keep the newest $RETENTION backups for this DB basename, delete the
# rest. Newest-first via reverse name sort (timestamps sort lexically).
log "applying retention: keep newest $RETENTION"
i=0
for f in $(ls -1 "$BACKUP_DIR"/"$DB_BASE".*.bak 2>/dev/null | sort -r); do
  i=$((i + 1))
  if [ "$i" -gt "$RETENTION" ]; then
    log "pruning old backup: $f"
    rm -f "$f"
  fi
done

# Optional offsite copy. rclone covers S3, GCS, B2, etc. via a configured remote.
if [ -n "${RCLONE_REMOTE:-}" ]; then
  command -v rclone >/dev/null 2>&1 || die "RCLONE_REMOTE set but 'rclone' not in PATH"
  log "copying offsite to '$RCLONE_REMOTE'"
  if ! rclone copy "$DEST" "$RCLONE_REMOTE"; then
    die "offsite copy to '$RCLONE_REMOTE' failed"
  fi
  log "offsite copy complete"
else
  log "RCLONE_REMOTE not set; skipping offsite copy"
fi

log "done"
