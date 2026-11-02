#!/usr/bin/env bash
# =============================================================================
# scripts/ejecutar_avisos.sh
# Invoca la revisión periódica de vencimientos y reenvío de multas en Préstamos.
# =============================================================================

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8002}"
ENDPOINT="${BASE_URL%/}/prestamos/revisar-vencimientos"

AUTH_ARGS=()
if [ -n "${BASIC_AUTH_USER:-}" ] && [ -n "${BASIC_AUTH_PASSWORD:-}" ]; then
  AUTH_ARGS=(-u "${BASIC_AUTH_USER}:${BASIC_AUTH_PASSWORD}")
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando revisión de vencimientos en: ${ENDPOINT}"

TEMP_FILE=$(mktemp)
HTTP_CODE=$(curl -s -S -X POST "${ENDPOINT}" \
  "${AUTH_ARGS[@]}" \
  -H "Content-Type: application/json" \
  -w "%{http_code}" \
  -o "${TEMP_FILE}" || echo "000")

RESPONSE_BODY=$(cat "${TEMP_FILE}")
rm -f "${TEMP_FILE}"

echo "HTTP Code: ${HTTP_CODE}"
echo "Respuesta: ${RESPONSE_BODY}"

if [ "${HTTP_CODE}" -ne 200 ]; then
  echo "[ERROR] La revisión de vencimientos falló (código HTTP: ${HTTP_CODE})" >&2
  exit 1
fi

echo "[SUCCESS] Revisión de vencimientos completada satisfactoriamente."
exit 0

