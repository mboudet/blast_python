#!/bin/bash
set -e

: ${APP_USER:='blast'}
: ${APP_GROUP:='blast'}

# Create the group, using the provided GID if any.
if ! getent group "$APP_GROUP" >/dev/null 2>&1; then
    if [ -n "$GID" ]; then
        groupadd --gid "$GID" "$APP_GROUP"
    else
        groupadd "$APP_GROUP"
    fi
fi

# Create the user, using the provided UID if any, attached to the group.
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    if [ -n "$UID" ]; then
        useradd --no-create-home --no-user-group --uid "$UID" --gid "$APP_GROUP" "$APP_USER"
    else
        useradd --no-create-home --no-user-group --gid "$APP_GROUP" "$APP_USER"
    fi
fi

# Ensure the application dir and jobs work dir are owned by the app user.
chown -R "$APP_USER":"$APP_GROUP" /srv/blast
: ${JOBS_WORK_DIR:='/tmp/'}
mkdir -p "$JOBS_WORK_DIR"
chown "$APP_USER":"$APP_GROUP" "$JOBS_WORK_DIR"

# Drop privileges and launch the webserver as the app user so that DRMAA/slurm
# jobs are submitted under that user.
exec setpriv --reuid "$APP_USER" --regid "$APP_GROUP" --init-groups \
    uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
