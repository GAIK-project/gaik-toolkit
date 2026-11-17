# The malware scanner the demo API checks every uploaded file with: a ClamAV daemon
# (clamd) on TCP 3310, with freshclam updating its signatures in the same
# container. See ../openshift/README.md, "Upload malware check".
#
# The signatures are downloaded at build time as well, so a new pod can scan as
# soon as clamd has loaded them, even before its first update gets through.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends clamav clamav-daemon clamav-freshclam ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY clamd.conf freshclam.conf /etc/clamav/
COPY entrypoint.sh /usr/local/bin/scanner-entrypoint

# The root filesystem is read-only in the pod: the signatures from the build
# are kept in /opt/clamav-db, and the entrypoint copies them into the writable
# /var/lib/clamav volume, where freshclam updates them.
RUN freshclam --foreground --stdout --config-file=/etc/clamav/freshclam.conf \
    && mkdir -p /opt/clamav-db \
    && cp -a /var/lib/clamav/. /opt/clamav-db/ \
    && chmod -R a+rX /opt/clamav-db \
    && chmod 0755 /usr/local/bin/scanner-entrypoint

USER 1001
EXPOSE 3310
ENTRYPOINT ["/usr/local/bin/scanner-entrypoint"]
