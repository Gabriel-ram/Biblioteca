#!/usr/bin/env bash
set -euo pipefail

BASE_NOTIF="http://127.0.0.1:8003"
BASE_MAILPIT="http://127.0.0.1:8025"

if command -v docker.exe >/dev/null 2>&1 && ! docker version >/dev/null 2>&1; then
    DOCKER_CMD="docker.exe"
else
    DOCKER_CMD="docker"
fi

get_json_field() {
    python -c "import sys, json; data = json.loads(sys.argv[1]); print(data.get(sys.argv[2], ''))" "$1" "$2"
}

get_mailpit_total() {
    python -c "import sys, json
try:
    print(json.loads(sys.argv[1]).get('total', 0))
except Exception:
    print(0)
" "$(curl -s "$BASE_MAILPIT/api/v1/messages")"
}

echo "===================================================================="
echo "VERIFICACIONES TRAS REVISIÓN (6a, 6b, 6h)"
echo "===================================================================="

# Limpiar Mailpit
echo "Limpiando buzón de Mailpit..."
curl -s -X DELETE "$BASE_MAILPIT/api/v1/messages" >/dev/null

# ------------------------------------------------------------------
# VERIFICACIÓN 6a: POST /notificar con ana@example.com y tipo PRESTAMO
# ------------------------------------------------------------------
echo ""
echo ">>> 6a: POST /notificar con ana@example.com y tipo PRESTAMO"
TIMESTAMP=$(date +%s)
CLAVE_6A="clave-rev-6a-$TIMESTAMP"

RESP_6A=$(curl -s -w "\n%{http_code}" -X POST "$BASE_NOTIF/notificar" \
    -H "Content-Type: application/json" \
    -d "{
        \"tipo\": \"PRESTAMO\",
        \"usuario\": \"Ana Garcia\",
        \"correo\": \"ana@example.com\",
        \"clave\": \"$CLAVE_6A\",
        \"datos\": {
            \"titulo\": \"Cien Anos de Soledad\",
            \"fecha_limite\": \"2026-11-20\"
        }
    }")

HTTP_6A=$(echo "$RESP_6A" | tail -n1)
BODY_6A=$(echo "$RESP_6A" | sed '$d')
echo "Código HTTP recibido: $HTTP_6A"
echo "Cuerpo de respuesta: $BODY_6A"

if [ "$HTTP_6A" -ne 202 ]; then
    echo "ERROR en 6a: Se esperaba 202, obtenido $HTTP_6A"
    exit 1
fi

ID_6A=$(get_json_field "$BODY_6A" "id")
DUPLICADA_6A=$(get_json_field "$BODY_6A" "duplicada")
echo "ID asignado: $ID_6A, duplicada: $DUPLICADA_6A"

echo "Esperando que el worker procese y envíe el correo a Mailpit..."
CORREO_LLEGO=0
for i in {1..10}; do
    TOTAL=$(get_mailpit_total)
    if [ "$TOTAL" -ge 1 ]; then
        CORREO_LLEGO=1
        echo "Correo detectado en Mailpit en ${i}s (total mensajes: $TOTAL)."
        break
    fi
    sleep 1
done

if [ "$CORREO_LLEGO" -ne 1 ]; then
    echo "ERROR en 6a: Correo no apareció en Mailpit dentro de 10s"
    exit 1
fi

# Inspeccionar correo recibido en Mailpit
MSG_JSON=$(curl -s "$BASE_MAILPIT/api/v1/messages")
echo "Detalle del mensaje en Mailpit:"
python -c "import sys, json
msg = json.loads(sys.argv[1])['messages'][0]
print(f\"  ID: {msg.get('ID')}\")
print(f\"  From: {msg.get('From', {}).get('Name')} <{msg.get('From', {}).get('Address')}>\")
print(f\"  To: {msg.get('To', [{}])[0].get('Address')}\")
print(f\"  Subject: {msg.get('Subject')}\")
print(f\"  Date: {msg.get('Created')}\")
print(f\"  Snippet: {msg.get('Snippet')}\")
" "$MSG_JSON"

# Verificar estado en base de datos
NOTIF_JSON=$(curl -s "$BASE_NOTIF/notificaciones")
python -c "import sys, json
data = json.loads(sys.argv[1])
target_id = sys.argv[2]
for x in data:
    if str(x.get('id')) == target_id:
        print(f'Estado en DB de la notificacion #{target_id}: {x.get(\"estado\")}')
        print(f'Fecha de envio en DB: {x.get(\"fecha_envio\")}')
        if x.get('estado') != 'ENVIADA':
            sys.exit(1)
        break
" "$NOTIF_JSON" "$ID_6A"
echo "[OK] Verificación 6a COMPLETADA EXITOSAMENTE."

# ------------------------------------------------------------------
# VERIFICACIÓN 6b: Repetir la misma clave (idempotencia)
# ------------------------------------------------------------------
echo ""
echo ">>> 6b: Repetir la misma clave ($CLAVE_6A)"
RESP_6B=$(curl -s -w "\n%{http_code}" -X POST "$BASE_NOTIF/notificar" \
    -H "Content-Type: application/json" \
    -d "{
        \"tipo\": \"PRESTAMO\",
        \"usuario\": \"Ana Garcia\",
        \"correo\": \"ana@example.com\",
        \"clave\": \"$CLAVE_6A\",
        \"datos\": {
            \"titulo\": \"Cien Anos de Soledad\",
            \"fecha_limite\": \"2026-11-20\"
        }
    }")

HTTP_6B=$(echo "$RESP_6B" | tail -n1)
BODY_6B=$(echo "$RESP_6B" | sed '$d')
echo "Código HTTP recibido: $HTTP_6B"
echo "Cuerpo de respuesta: $BODY_6B"

if [ "$HTTP_6B" -ne 202 ]; then
    echo "ERROR en 6b: Se esperaba 202, obtenido $HTTP_6B"
    exit 1
fi

DUPLICADA_6B=$(get_json_field "$BODY_6B" "duplicada")
ID_6B=$(get_json_field "$BODY_6B" "id")

if [ "$DUPLICADA_6B" != "True" ] && [ "$DUPLICADA_6B" != "true" ]; then
    echo "ERROR en 6b: duplicada debió ser True, obtenido $DUPLICADA_6B"
    exit 1
fi

if [ "$ID_6B" != "$ID_6A" ]; then
    echo "ERROR en 6b: id devuelto ($ID_6B) no coincide con el original ($ID_6A)"
    exit 1
fi

sleep 2
TOTAL_6B=$(get_mailpit_total)
echo "Total de correos en Mailpit tras reintento duplicado: $TOTAL_6B"
if [ "$TOTAL_6B" -ne 1 ]; then
    echo "ERROR en 6b: Se esperaba exactamente 1 correo en Mailpit, hay $TOTAL_6B"
    exit 1
fi
echo "[OK] Verificación 6b COMPLETADA EXITOSAMENTE."

# ------------------------------------------------------------------
# VERIFICACIÓN 6h: Auditoría de logs de seguridad
# ------------------------------------------------------------------
echo ""
echo ">>> 6h: Auditoría de logs de seguridad en notificaciones"
LOGS=$($DOCKER_CMD compose logs --tail=50 notificaciones)

echo "Verificando ausencia de contraseñas y correos completos..."
if echo "$LOGS" | grep -iE "password|contraseña" | grep -v "SMTP_PASSWORD"; then
    echo "ERROR en 6h: Se detectó una posible contraseña en los logs"
    exit 1
fi

if echo "$LOGS" | grep -q "ana@example.com"; then
    echo "ERROR en 6h: Correo completo ana@example.com encontrado en logs"
    exit 1
fi

if echo "$LOGS" | grep -q "a\*\*\*@example.com"; then
    echo "Confirmado: los correos se registran con máscara 'a***@example.com' en logs."
fi

echo "Muestra de logs recientes del worker:"
echo "$LOGS" | grep -E "notificaciones.worker|ALERTA DE NOTIFICACIÓN" | tail -n 10
echo "[OK] Verificación 6h COMPLETADA EXITOSAMENTE."

echo ""
echo "===================================================================="
echo "TODAS LAS VERIFICACIONES (6a, 6b, 6h) PASARON EXITOSAMENTE"
echo "===================================================================="
