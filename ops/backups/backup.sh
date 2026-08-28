#!/bin/sh

# Mosaic Budget PostgreSQL backup service.
#
# The regular container process runs this continuously. Setting
# MOSAIC_BACKUP_ONCE=1 performs one verified backup and exits; Makefile uses
# that mode for an on-demand backup inside the existing container.

set -u
umask 077

BACKUP_DIR=${BACKUP_DIR:-/backups}
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-35}
BACKUP_INTERVAL_SECONDS=${BACKUP_INTERVAL_SECONDS:-86400}
BACKUP_RETRY_SECONDS=${BACKUP_RETRY_SECONDS:-300}
BACKUP_LOCK_WAIT_SECONDS=${BACKUP_LOCK_WAIT_SECONDS:-300}
LOCK_FILE=${BACKUP_LOCK_FILE:-/tmp/mosaic-backup.lock}
LOCK_CANDIDATE="${LOCK_FILE}.$$"
PGCONNECT_TIMEOUT=${PGCONNECT_TIMEOUT:-10}
export PGCONNECT_TIMEOUT

backup_lock_held=0
backup_partial_path=
backup_verify_database=
backup_verify_database_created=0

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

is_nonnegative_integer() {
    case $1 in
        ''|*[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

is_positive_integer() {
    is_nonnegative_integer "$1" && [ "$1" -gt 0 ]
}

release_lock() {
    # The candidate name includes this process's PID, so removing it cannot
    # disturb another backup attempt.
    rm -f "$LOCK_CANDIDATE"

    if [ "$backup_lock_held" -ne 1 ]; then
        return
    fi

    lock_owner=
    if [ -r "$LOCK_FILE" ]; then
        IFS= read -r lock_owner < "$LOCK_FILE" || true
    fi
    if [ "$lock_owner" = "$$" ]; then
        rm -f "$LOCK_FILE"
    fi
    backup_lock_held=0
}

drop_verification_database() {
    if [ "$backup_verify_database_created" -ne 1 ]; then
        backup_verify_database=
        return 0
    fi

    if dropdb --no-password --if-exists "$backup_verify_database"; then
        backup_verify_database=
        backup_verify_database_created=0
        return 0
    fi

    log "ERROR: could not remove verification database $backup_verify_database"
    return 1
}

cleanup_attempt() {
    cleanup_status=0
    if ! drop_verification_database; then
        cleanup_status=1
    fi
    if [ -n "$backup_partial_path" ]; then
        rm -f "$backup_partial_path"
        backup_partial_path=
    fi
    release_lock
    return "$cleanup_status"
}

cleanup_on_exit() {
    exit_status=$?
    trap - 0 HUP INT TERM
    if ! cleanup_attempt && [ "$exit_status" -eq 0 ]; then
        exit_status=1
    fi
    exit "$exit_status"
}

trap cleanup_on_exit 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

recover_stale_lock() {
    stale_owner=
    if [ -r "$LOCK_FILE" ]; then
        IFS= read -r stale_owner < "$LOCK_FILE" || true
    fi

    case $stale_owner in
        ''|*[!0-9]*) ;;
        *)
            if kill -0 "$stale_owner" 2>/dev/null; then
                return 1
            fi
            ;;
    esac

    rm -f "$LOCK_FILE"
}

acquire_lock() {
    waited=0

    rm -f "$LOCK_CANDIDATE"
    if ! printf '%s\n' "$$" > "$LOCK_CANDIDATE"; then
        log "ERROR: cannot create lock candidate $LOCK_CANDIDATE"
        return 1
    fi

    while :; do
        # The candidate already contains our PID. Hard-link publication is
        # atomic, so contenders cannot observe an initialized-but-empty lock.
        backup_lock_held=1
        if ln "$LOCK_CANDIDATE" "$LOCK_FILE" 2>/dev/null; then
            rm -f "$LOCK_CANDIDATE"
            return 0
        fi
        backup_lock_held=0

        # Retry publication immediately when a stale lock was removed. This
        # also makes BACKUP_LOCK_WAIT_SECONDS=0 useful for an uncontended or
        # stale-lock recovery attempt.
        if recover_stale_lock; then
            continue
        fi
        if [ "$waited" -ge "$BACKUP_LOCK_WAIT_SECONDS" ]; then
            rm -f "$LOCK_CANDIDATE"
            log "ERROR: another backup still holds $LOCK_FILE after ${BACKUP_LOCK_WAIT_SECONDS}s"
            return 1
        fi
        if [ "$waited" -eq 0 ]; then
            log "Another backup is active; waiting for it to finish"
        fi
        sleep 1
        waited=$((waited + 1))
    done
}

fail_attempt() {
    log "ERROR: $*"
    cleanup_attempt || true
    return 1
}

perform_backup() {
    acquire_lock || return 1

    # Avoid replacing a same-second backup when a scheduled run and a manual
    # run occur back-to-back.
    while :; do
        backup_timestamp=$(date -u '+%Y%m%dT%H%M%SZ')
        backup_final_path="$BACKUP_DIR/mosaic-$backup_timestamp.dump"
        if [ ! -e "$backup_final_path" ]; then
            break
        fi
        sleep 1
    done

    backup_partial_path="$backup_final_path.partial"
    backup_verify_database="mosaic_verify_${backup_timestamp}_$$"
    backup_verify_database_created=0

    log "Creating PostgreSQL backup $backup_final_path"
    if ! pg_dump \
        --no-password \
        --format=custom \
        --file="$backup_partial_path" \
        --dbname="$PGDATABASE"; then
        fail_attempt "pg_dump failed"
        return 1
    fi

    if [ ! -s "$backup_partial_path" ]; then
        fail_attempt "pg_dump produced an empty archive"
        return 1
    fi
    if ! pg_restore --list "$backup_partial_path" >/dev/null; then
        fail_attempt "the dump archive cannot be read by pg_restore"
        return 1
    fi

    log "Restoring backup into temporary database $backup_verify_database"
    if ! createdb --no-password --template=template0 "$backup_verify_database"; then
        fail_attempt "could not create the verification database"
        return 1
    fi
    backup_verify_database_created=1
    if ! pg_restore \
        --no-password \
        --exit-on-error \
        --no-owner \
        --no-privileges \
        --dbname="$backup_verify_database" \
        "$backup_partial_path"; then
        fail_attempt "restore verification failed"
        return 1
    fi

    verified_schema=$(psql \
        --no-password \
        --dbname="$backup_verify_database" \
        --no-align \
        --tuples-only \
        --quiet \
        --set=ON_ERROR_STOP=1 \
        <<'SQL'
SELECT CASE WHEN
    to_regclass('public.alembic_version') IS NOT NULL
    AND to_regclass('public.workspaces') IS NOT NULL
    AND to_regclass('public.users') IS NOT NULL
    AND to_regclass('public.accounts') IS NOT NULL
    AND to_regclass('public.budget_transactions') IS NOT NULL
    AND to_regclass('public.source_transactions') IS NOT NULL
    AND to_regclass('public.backup_records') IS NOT NULL
THEN 'ok' ELSE 'missing-core-tables' END;
SQL
    )
    if [ "$verified_schema" != "ok" ]; then
        fail_attempt "restored database is missing one or more core tables"
        return 1
    fi

    if ! drop_verification_database; then
        fail_attempt "verification database cleanup failed"
        return 1
    fi

    if ! chmod 600 "$backup_partial_path" || ! mv "$backup_partial_path" "$backup_final_path"; then
        fail_attempt "could not finalize the verified archive"
        return 1
    fi
    backup_partial_path=

    backup_byte_size=$(wc -c < "$backup_final_path" | tr -d '[:space:]')
    if ! is_positive_integer "$backup_byte_size"; then
        fail_attempt "could not determine the verified archive size"
        return 1
    fi

    if ! psql \
        --no-password \
        --dbname="$PGDATABASE" \
        --quiet \
        --set=ON_ERROR_STOP=1 \
        --set=backup_path="$backup_final_path" \
        --set=backup_byte_size="$backup_byte_size" \
        <<'SQL'
INSERT INTO backup_records (id, path, byte_size, verified_at)
VALUES (gen_random_uuid(), :'backup_path', :backup_byte_size, CURRENT_TIMESTAMP);
SQL
    then
        fail_attempt "archive was verified, but its backup record could not be written"
        return 1
    fi

    # Retention runs only after dump, restore, schema checks, and recording all
    # succeed. It deliberately targets Mosaic's finalized .dump files only.
    if ! find "$BACKUP_DIR" \
        -type f \
        -name 'mosaic-*.dump' \
        -mtime "+$BACKUP_RETENTION_DAYS" \
        -exec rm -f {} \;
    then
        log "WARNING: backup succeeded, but retention cleanup encountered an error"
    fi

    release_lock
    log "Verified backup complete: $backup_final_path ($backup_byte_size bytes)"
    return 0
}

if ! is_nonnegative_integer "$BACKUP_RETENTION_DAYS"; then
    log "ERROR: BACKUP_RETENTION_DAYS must be a non-negative integer"
    exit 2
fi
if ! is_positive_integer "$BACKUP_INTERVAL_SECONDS"; then
    log "ERROR: BACKUP_INTERVAL_SECONDS must be a positive integer"
    exit 2
fi
if ! is_positive_integer "$BACKUP_RETRY_SECONDS"; then
    log "ERROR: BACKUP_RETRY_SECONDS must be a positive integer"
    exit 2
fi
if ! is_nonnegative_integer "$BACKUP_LOCK_WAIT_SECONDS"; then
    log "ERROR: BACKUP_LOCK_WAIT_SECONDS must be a non-negative integer"
    exit 2
fi
if ! is_positive_integer "$PGCONNECT_TIMEOUT"; then
    log "ERROR: PGCONNECT_TIMEOUT must be a positive integer"
    exit 2
fi
if [ -z "${PGDATABASE:-}" ]; then
    log "ERROR: PGDATABASE is required"
    exit 2
fi
if ! mkdir -p "$BACKUP_DIR"; then
    log "ERROR: cannot create backup directory $BACKUP_DIR"
    exit 2
fi
if ! backup_dir_resolved=$(
    CDPATH=
    cd "$BACKUP_DIR" 2>/dev/null && pwd -P
); then
    log "ERROR: cannot resolve backup directory $BACKUP_DIR"
    exit 2
fi
if [ "$backup_dir_resolved" = "/" ]; then
    log "ERROR: BACKUP_DIR must not resolve to the filesystem root"
    exit 2
fi
BACKUP_DIR=$backup_dir_resolved

if [ "${MOSAIC_BACKUP_ONCE:-0}" = "1" ]; then
    perform_backup
    exit $?
fi

while :; do
    if perform_backup; then
        sleep "$BACKUP_INTERVAL_SECONDS"
    else
        log "Backup failed; retrying in ${BACKUP_RETRY_SECONDS}s"
        sleep "$BACKUP_RETRY_SECONDS"
    fi
done
