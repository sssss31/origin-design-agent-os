#!/usr/bin/env bash
# Run an isolated PostgreSQL 17 cluster for local development without Docker.
#   scripts/local-postgres.sh start|stop|status|init
# Data lives in .data/pg17 (gitignored). Port 55432, superuser pathsense_test/pathsense_test.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/.data/pg17"
PORT="${PGPORT_LOCAL:-55432}"
BIN="${PG_BIN:-$(ls -d /opt/homebrew/opt/postgresql@17/bin /usr/lib/postgresql/17/bin 2>/dev/null | head -1)}"
export LC_ALL=C   # macOS: avoids "postmaster became multithreaded" on start
init() {
  if [ -f "$DATA/PG_VERSION" ]; then echo "cluster exists at $DATA"; return; fi
  mkdir -p "$(dirname "$DATA")"
  local pw; pw="$(mktemp)"; echo pathsense_test > "$pw"
  "$BIN/initdb" -D "$DATA" -U pathsense_test --pwfile="$pw" -A scram-sha-256 -E UTF8 --locale=C >/dev/null
  rm -f "$pw"; echo "initialised $DATA"
}
start() {
  init
  "$BIN/pg_ctl" -D "$DATA" -o "-p $PORT" -l "$DATA.log" start
  sleep 2
  for db in origin_dev origin_test; do
    PGPASSWORD=pathsense_test psql -h localhost -p "$PORT" -U pathsense_test -d postgres -Atc "select 1 from pg_database where datname='$db'" | grep -q 1 \
      || PGPASSWORD=pathsense_test psql -h localhost -p "$PORT" -U pathsense_test -d postgres -qc "create database $db"
  done
  echo "DATABASE_URL=postgresql+psycopg://pathsense_test:pathsense_test@localhost:$PORT/origin_dev"
}
case "${1:-status}" in
  init) init ;;
  start) start ;;
  stop) "$BIN/pg_ctl" -D "$DATA" stop ;;
  status) "$BIN/pg_ctl" -D "$DATA" status || true; pg_isready -h localhost -p "$PORT" || true ;;
  *) echo "usage: $0 start|stop|status|init"; exit 1 ;;
esac
