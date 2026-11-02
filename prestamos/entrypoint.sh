#!/bin/sh
# entrypoint.sh — Ajusta permisos de /data (volúmenes existentes pueden ser de root)
# y luego ejecuta el CMD como el usuario nobody.
set -e

chown -R nobody:nogroup /data 2>/dev/null || true

# Ejecutar CMD como nobody
exec runuser -u nobody -- "$@"
