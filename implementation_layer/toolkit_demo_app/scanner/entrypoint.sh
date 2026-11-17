#!/bin/sh
# /var/lib/clamav is a writable volume that starts empty: copy in the
# signatures from the build, then let freshclam keep them current in the
# background (it forks itself). clamd stays in the foreground as the
# container's main process.
set -eu
if ! ls /var/lib/clamav/*.c[lv]d >/dev/null 2>&1; then
    cp /opt/clamav-db/* /var/lib/clamav/
fi
freshclam --daemon --stdout --config-file=/etc/clamav/freshclam.conf || echo "freshclam did not start; scanning with the signatures in the image" >&2
exec clamd --config-file=/etc/clamav/clamd.conf
