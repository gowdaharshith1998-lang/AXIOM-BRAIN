#!/bin/sh
# restore_db.sh — restore the AXIOM SQLite DB from a backup (P1-7 / DB-004).
#
# Restores a chosen backup file over the live DB. Before overwriting, it takes a
# pre-restore safety copy of the current DB (so a bad restore is reversible).
# After restoring, it runs PRAGMA integrity_check and prints the Alembic schema
# version so the operator can confirm the restored schema matches the running
# code. WAL sidecar files (-wal/-shm) of the live DB are removed so the restored
# DB is the single source of truth on next open.
#
# STOP THE APP (and any organizer/ingest writer) before running this. Restoring
# under an open writer risks an inconsistent on-disk state.
#
# Usage:
#   scripts/restore_db.sh BACKUP_FILE [DB_PATH]
#
# Environment:
#   AXIOM_DB_PATH   Path to the live SQLite DB to overwrite (default: /data/axiom.db)
#   SQLITE_BIN      sqlite3 binary                          (default: sqlite3)
#   ALEMBIC_BIN     alembic binary for version display      (default: alembic)
#
# Exit codes: 0 ok, non-zero on any failure.

set -eu

log() { printf '%s [restore_db] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

[ "$#" -ge 1 ] || die "usage: restore_db.sh BACKUP_FILE [DB_PATH]"

BACKUP_FILE="$1"
DB_PATH="${2:-${AXIOM_DB_PATH:-/data/axiom.db}}"
SQLITE_BIN="${SQLITE_BIN:-sqlite3}"
ALEMBIC_BIN="${ALEMBIC_BIN:-alembic}"

command -v "$SQLITE_BIN" >/dev/null 2>&1 || die "sqlite3 binary '$SQLITE_BIN' not found in PATH"

[ -f "$BACKUP_FILE" ] || die "backup file '$BACKUP_FILE' not found"
[ -r "$BACKUP_FILE" ] || die "backup file '$BACKUP_FILE' not readable"

# Validate the backup itself BEFORE touching the live DB. Never restore from a
# corrupt source.
log "validating backup '$BACKUP_FILE'"
CHECK="$("$SQLITE_BIN" "$BACKUP_FILE" 'PRAGMA integrity_check;' 2>&1)" \
  || die "could not run integrity_check on backup: $CHECK"
[ "$CHECK" = "ok" ] || die "backup '$BACKUP_FILE' is corrupt (integrity_check: $CHECK); refusing to restore"
log "backup integrity_check ok"

DB_DIR="$(dirname "$DB_PATH")"
mkdir -p "$DB_DIR" || die "cannot create DB dir '$DB_DIR'"
[ -w "$DB_DIR" ] || die "DB dir '$DB_DIR' is not writable"

TIMESTAMP="$(date -u '+%Y%m%dT%H%M%SZ')"

# Pre-restore safety copy of the current DB so the restore is reversible.
if [ -f "$DB_PATH" ]; then
  SAFETY="${DB_PATH}.pre-restore.${TIMESTAMP}.bak"
  log "saving pre-restore safety copy of current DB -> '$SAFETY'"
  if ! "$SQLITE_BIN" "$DB_PATH" ".backup '$SAFETY'" 2>/dev/null; then
    # The current DB may be corrupt or locked; fall back to a raw copy so we
    # still have *something* to roll back to.
    log "online .backup of current DB failed; falling back to raw copy"
    cp "$DB_PATH" "$SAFETY" || die "could not create safety copy '$SAFETY'"
  fi
  log "safety copy written: $SAFETY"
else
  log "no existing DB at '$DB_PATH'; nothing to back up before restore"
fi

# Remove stale WAL/SHM sidecars of the live DB so the restored file is the sole
# source of truth on next open (a leftover -wal would replay onto the new file).
for sidecar in "${DB_PATH}-wal" "${DB_PATH}-shm"; do
  if [ -e "$sidecar" ]; then
    log "removing stale sidecar '$sidecar'"
    rm -f "$sidecar"
  fi
done

# Restore using the SQLite restore path: read the backup and write into a fresh
# copy at DB_PATH. We use a plain copy here because the source is a static file
# and the app is stopped; this avoids partial-page issues from `.backup` onto an
# existing file.
RESTORE_TMP="${DB_PATH}.restore.${TIMESTAMP}.partial"
log "restoring '$BACKUP_FILE' -> '$DB_PATH'"
cp "$BACKUP_FILE" "$RESTORE_TMP" || die "could not stage restore copy"
mv "$RESTORE_TMP" "$DB_PATH" || { rm -f "$RESTORE_TMP"; die "could not move restored DB into place"; }

# Post-restore integrity check on the now-live DB.
log "verifying restored DB"
CHECK="$("$SQLITE_BIN" "$DB_PATH" 'PRAGMA integrity_check;' 2>&1)" \
  || die "could not run integrity_check on restored DB: $CHECK"
[ "$CHECK" = "ok" ] || die "restored DB FAILED integrity_check: $CHECK"
log "restored DB integrity_check ok"

# Display the Alembic schema version so the operator can confirm it matches the
# running code (run `alembic upgrade head` if the restored DB is older).
STAMP="$("$SQLITE_BIN" "$DB_PATH" 'SELECT version_num FROM alembic_version;' 2>/dev/null || true)"
if [ -n "$STAMP" ]; then
  log "restored Alembic version (from alembic_version table): $STAMP"
else
  log "WARNING: no alembic_version row found in restored DB"
fi

if command -v "$ALEMBIC_BIN" >/dev/null 2>&1; then
  log "alembic current (against DATABASE_URL):"
  "$ALEMBIC_BIN" current 2>&1 | sed 's/^/  /' >&2 || log "WARNING: 'alembic current' failed (check DATABASE_URL / cwd)"
  log "alembic head (latest revision known to code):"
  "$ALEMBIC_BIN" heads 2>&1 | sed 's/^/  /' >&2 || log "WARNING: 'alembic heads' failed"
  log "if 'current' is behind 'head', run: alembic upgrade head"
else
  log "alembic binary not found; skipping live alembic current/heads display"
fi

log "restore complete. Start the app and confirm /readyz is healthy."
