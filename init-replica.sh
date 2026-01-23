#!/bin/bash
set -e

echo "Waiting for master to be ready..."
until PGPASSWORD=apppass pg_isready -h pg-master -U appuser; do
    sleep 2
done

echo "Master ready. Creating base backup..."
rm -rf /var/lib/postgresql/data/*

PGPASSWORD=replicapass pg_basebackup \
    -h pg-master \
    -U replicator \
    -D /var/lib/postgresql/data \
    -Fp -Xs -P -R

chmod 700 /var/lib/postgresql/data
chown -R postgres:postgres /var/lib/postgresql/data

echo "Starting replica as postgres user..."
exec su-exec postgres postgres -c hot_standby=on
