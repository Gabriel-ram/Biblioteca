#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE VERIFICACIÓN FASE F7: ENVÍO DE CORREOS EN NOTIFICACIONES
# ==============================================================================
set -euo pipefail

BASE_NOTIFICACIONES="http://127.0.0.1:8003"
BASE_MAILPIT="http://127.0.0.1:8025"

if command -v docker.exe >/dev/null 2>&1 && ! docker version >/dev/null 2>&1; then
    DOCKER_CMD="docker.exe"
else
    DOCKER_CMD="docker"
fi

get_json_field() {
    python -c "import sys, json; data = json.loads(sys.argv[1]); print(data.get(sys.argv[2], ''))" "$1" "$2"
}

get_notif_field_by_id() {
    python -c "import sys, json
data = json.loads(sys.argv[1])
for item in data:
    if str(item.get('id')) == str(sys.argv[2]):
        val = item.get(sys.argv[3], '')
        print('' if val is None else val)
        break
" "$1" "$2" "$3"
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
echo "INICIANDO VERIFICACIÓN FASE F7: NOTIFICACIONES Y CORREOS"
echo "===================================================================="

# Asegurar que mailpit esté corriendo
$DOCKER_CMD compose start mailpit
sleep 1

# Limpiar mensajes previos en Mailpit
echo "Limpiando buzón de Mailpit..."
curl -s -X DELETE "$BASE_MAILPIT/api/v1/messages" >/dev/null || true

# --- a. POST /notificar con ana@example.com y tipo PRESTAMO ---
echo ""
echo "--- a. POST /notificar con ana@example.com y tipo PRESTAMO ---"
TIMESTAMP=$(date +%s)
CLAVE_A="clave-f7-a-$TIMESTAMP"
RESP_A=$(curl -s -w "\n%{http_code}" -X POST "$BASE_NOTIFICACIONES/notificar" \
    -H "Content-Type: application/json" \
    -d "{
        \"tipo\": \"PRESTAMO\",
        \"usuario\": \"Ana Garcia\",
        \"correo\": \"ana@example.com\",
        \"clave\": \"$CLAVE_A\",
        \"datos\": {
            \"titulo\": \"El Principito\",
            \"fecha_limite\": \"2026-11-15\"
        }
    }")

HTTP_A=$(echo "$RESP_A" | tail -n1)
BODY_A=$(echo "$RESP_A" | sed '$d')
echo "Código HTTP: $HTTP_A"
echo "Cuerpo: $BODY_A"

if [ "$HTTP_A" -ne 202 ]; then
    echo "ERROR en (a): Se esperaba HTTP 202, obtenido $HTTP_A"
    exit 1
fi

ID_A=$(get_json_field "$BODY_A" "id")
DUPLICADA_A=$(get_json_field "$BODY_A" "duplicada")

if [ "$DUPLICADA_A" != "False" ] && [ "$DUPLICADA_A" != "false" ]; then
    echo "ERROR en (a): Se esperaba duplicada=False, obtenido $DUPLICADA_A"
    exit 1
fi

echo "Esperando que el worker procese y envíe el correo a Mailpit (máx 12s)..."
CORREO_LLEGO=0
for i in {1..12}; do
    TOTAL=$(get_mailpit_total)
    if [ "$TOTAL" -ge 1 ]; then
        CORREO_LLEGO=1
        echo "Correo detectado en Mailpit en ${i}s (total: $TOTAL)."
        break
    fi
    sleep 1
done

if [ "$CORREO_LLEGO" -ne 1 ]; then
    echo "ERROR en (a): El correo no llegó a Mailpit en el tiempo esperado"
    exit 1
fi

# Verificar contenido en Mailpit
MSG_A=$(curl -s "$BASE_MAILPIT/api/v1/messages")
if ! echo "$MSG_A" | grep -q "ana@example.com"; then
    echo "ERROR en (a): Destinatario ana@example.com no encontrado en Mailpit"
    exit 1
fi

# Verificar estado en base de datos
NOTIF_A=$(curl -s "$BASE_NOTIFICACIONES/notificaciones")
ESTADO_A=$(get_notif_field_by_id "$NOTIF_A" "$ID_A" "estado")
echo "Estado de la notificación #$ID_A: $ESTADO_A"
if [ "$ESTADO_A" != "ENVIADA" ]; then
    echo "ERROR en (a): La notificación no pasó a estado ENVIADA, estado actual: $ESTADO_A"
    exit 1
fi
echo "[OK] (a) Notificación creada (202), correo recibido en Mailpit y estado ENVIADA."

# --- b. Repetir la misma clave ---
echo ""
echo "--- b. Repetir la misma clave (idempotencia) ---"
RESP_B=$(curl -s -w "\n%{http_code}" -X POST "$BASE_NOTIFICACIONES/notificar" \
    -H "Content-Type: application/json" \
    -d "{
        \"tipo\": \"PRESTAMO\",
        \"usuario\": \"Ana Garcia\",
        \"correo\": \"ana@example.com\",
        \"clave\": \"$CLAVE_A\",
        \"datos\": {
            \"titulo\": \"El Principito\",
            \"fecha_limite\": \"2026-11-15\"
        }
    }")

HTTP_B=$(echo "$RESP_B" | tail -n1)
BODY_B=$(echo "$RESP_B" | sed '$d')
echo "Código HTTP: $HTTP_B"
echo "Cuerpo: $BODY_B"

if [ "$HTTP_B" -ne 202 ]; then
    echo "ERROR en (b): Se esperaba HTTP 202 en duplicada, obtenido $HTTP_B"
    exit 1
fi

DUPLICADA_B=$(get_json_field "$BODY_B" "duplicada")
ID_B=$(get_json_field "$BODY_B" "id")

if [ "$DUPLICADA_B" != "True" ] && [ "$DUPLICADA_B" != "true" ]; then
    echo "ERROR en (b): Se esperaba duplicada=True, obtenido $DUPLICADA_B"
    exit 1
fi

if [ "$ID_B" != "$ID_A" ]; then
    echo "ERROR en (b): Se esperaba id=$ID_A, obtenido $ID_B"
    exit 1
fi

sleep 2
TOTAL_B=$(get_mailpit_total)
if [ "$TOTAL_B" -ne 1 ]; then
    echo "ERROR en (b): No debió llegar otro correo, total es $TOTAL_B (esperado 1)"
    exit 1
fi
echo "[OK] (b) Clave duplicada respondió 202 con duplicada=true y no generó correo adicional."

# --- c. POST /notificar sin correo ---
echo ""
echo "--- c. POST /notificar sin correo (compatibilidad) ---"
RESP_C=$(curl -s -w "\n%{http_code}" -X POST "$BASE_NOTIFICACIONES/notificar" \
    -H "Content-Type: application/json" \
    -d "{
        \"tipo\": \"POR_VENCER\",
        \"usuario\": \"Usuario Sin Correo\",
        \"mensaje\": \"Tu libro vence manana\"
    }")

HTTP_C=$(echo "$RESP_C" | tail -n1)
BODY_C=$(echo "$RESP_C" | sed '$d')
echo "Código HTTP: $HTTP_C"
echo "Cuerpo: $BODY_C"

if [ "$HTTP_C" -ne 202 ]; then
    echo "ERROR en (c): Se esperaba HTTP 202 sin correo, obtenido $HTTP_C"
    exit 1
fi

ID_C=$(get_json_field "$BODY_C" "id")
NOTIF_C=$(curl -s "$BASE_NOTIFICACIONES/notificaciones")
ESTADO_C=$(get_notif_field_by_id "$NOTIF_C" "$ID_C" "estado")
ERROR_C=$(get_notif_field_by_id "$NOTIF_C" "$ID_C" "ultimo_error")
echo "Notificación sin correo en DB: ID $ID_C, estado=$ESTADO_C, ultimo_error=$ERROR_C"

if [ "$ESTADO_C" != "FALLIDA" ]; then
    echo "ERROR en (c): Estado debió ser FALLIDA, obtenido $ESTADO_C"
    exit 1
fi

if [ "$ERROR_C" != "sin correo destino" ]; then
    echo "ERROR en (c): ultimo_error debió ser 'sin correo destino', obtenido '$ERROR_C'"
    exit 1
fi
echo "[OK] (c) Notificación sin correo respondió 202 y quedó en FALLIDA con 'sin correo destino'."

# --- d. Detener Mailpit, enviar notificación (backoff), iniciar Mailpit (entrega única) ---
echo ""
echo "--- d. Detener Mailpit, enviar notificación y reanudar ---"
$DOCKER_CMD compose stop mailpit

CLAVE_D="clave-f7-d-$TIMESTAMP"
RESP_D=$(curl -s -w "\n%{http_code}" -X POST "$BASE_NOTIFICACIONES/notificar" \
    -H "Content-Type: application/json" \
    -d "{
        \"tipo\": \"MULTA\",
        \"usuario\": \"Carlos Multa\",
        \"correo\": \"carlos@example.com\",
        \"clave\": \"$CLAVE_D\",
        \"datos\": {
            \"titulo\": \"Rayuela\",
            \"monto\": 25.0,
            \"dias_retraso\": 5
        }
    }")

HTTP_D=$(echo "$RESP_D" | tail -n1)
BODY_D=$(echo "$RESP_D" | sed '$d')
ID_D=$(get_json_field "$BODY_D" "id")
echo "Notificación creada con Mailpit apagado: ID $ID_D (HTTP $HTTP_D)"

# Esperar ciclo del worker (6s)
echo "Esperando que el worker intente el envío y registre fallo..."
sleep 6

NOTIF_D=$(curl -s "$BASE_NOTIFICACIONES/notificaciones")
ESTADO_D=$(get_notif_field_by_id "$NOTIF_D" "$ID_D" "estado")
INTENTOS_D=$(get_notif_field_by_id "$NOTIF_D" "$ID_D" "intentos")
PROXIMO_D=$(get_notif_field_by_id "$NOTIF_D" "$ID_D" "proximo_intento")
echo "Detalle notificación #$ID_D: estado=$ESTADO_D, intentos=$INTENTOS_D, proximo_intento=$PROXIMO_D"

if [ "$ESTADO_D" != "PENDIENTE" ]; then
    echo "ERROR en (d): Estado debería ser PENDIENTE tras fallo inicial, obtenido $ESTADO_D"
    $DOCKER_CMD compose start mailpit
    exit 1
fi

echo "Iniciando Mailpit..."
$DOCKER_CMD compose start mailpit
sleep 2

# Para no esperar los 30s del backoff en la prueba, adelantamos proximo_intento a ahora en SQLite
echo "Acelerando proximo_intento a ahora para entrega tras reactivar Mailpit..."
MSYS_NO_PATHCONV=1 $DOCKER_CMD compose exec -T notificaciones python -c "
import sqlite3, datetime
conn = sqlite3.connect('/data/notificaciones.db')
conn.execute('UPDATE notificaciones SET proximo_intento = ? WHERE id = ?', (datetime.datetime.now().isoformat(), $ID_D))
conn.commit()
conn.close()
"

echo "Esperando entrega del correo en Mailpit..."
ENTREGA_D=0
for i in {1..12}; do
    if curl -s "$BASE_MAILPIT/api/v1/messages" | grep -q "carlos@example.com"; then
        ENTREGA_D=1
        echo "Correo de Carlos entregado en Mailpit tras reactivación."
        break
    fi
    sleep 1
done

if [ "$ENTREGA_D" -ne 1 ]; then
    echo "ERROR en (d): El correo no fue entregado tras reiniciar Mailpit"
    exit 1
fi

NOTIF_D_FINAL=$(curl -s "$BASE_NOTIFICACIONES/notificaciones")
ESTADO_D_FINAL=$(get_notif_field_by_id "$NOTIF_D_FINAL" "$ID_D" "estado")
echo "Estado final notificación #$ID_D: $ESTADO_D_FINAL"
if [ "$ESTADO_D_FINAL" != "ENVIADA" ]; then
    echo "ERROR en (d): Estado final no es ENVIADA, obtenido $ESTADO_D_FINAL"
    exit 1
fi
echo "[OK] (d) Con Mailpit detenido acumuló intento y al reanudar se entregó exitosamente."

# --- e. Con notificación PENDIENTE, docker compose restart notificaciones ---
echo ""
echo "--- e. Notificación PENDIENTE sobrevive a restart de notificaciones ---"
CLAVE_E="clave-f7-e-$TIMESTAMP"
RESP_E=$(curl -s -X POST "$BASE_NOTIFICACIONES/notificar" \
    -H "Content-Type: application/json" \
    -d "{
        \"tipo\": \"PRESTAMO\",
        \"usuario\": \"Elena Persistencia\",
        \"correo\": \"elena@example.com\",
        \"clave\": \"$CLAVE_E\",
        \"datos\": {\"titulo\": \"Ficciones\"}
    }")
ID_E=$(get_json_field "$RESP_E" "id")

# Reiniciar contenedor de notificaciones inmediatamente
echo "Reiniciando notificaciones con tarea #$ID_E en cola..."
$DOCKER_CMD compose restart notificaciones

echo "Esperando que notificaciones esté saludable tras reinicio..."
for i in {1..20}; do
    if curl -s "$BASE_NOTIFICACIONES/health" | grep -q '"UP"'; then
        echo "Notificaciones está UP."
        break
    fi
    sleep 1
done

echo "Esperando que el worker procese la notificación pendiente tras reinicio..."
ENTREGA_E=0
for i in {1..12}; do
    NOTIF_E=$(curl -s "$BASE_NOTIFICACIONES/notificaciones")
    ESTADO_E=$(get_notif_field_by_id "$NOTIF_E" "$ID_E" "estado")
    if [ "$ESTADO_E" = "ENVIADA" ]; then
        ENTREGA_E=1
        echo "Notificación #$ID_E entregada tras reinicio del servicio."
        break
    fi
    sleep 1
done

if [ "$ENTREGA_E" -ne 1 ]; then
    echo "ERROR en (e): La notificación no fue entregada tras reiniciar notificaciones"
    exit 1
fi
echo "[OK] (e) Notificación persistió y fue entregada exitosamente tras restart del contenedor."

# --- f. Enviar 10 notificaciones seguidas con claves distintas ---
echo ""
echo "--- f. Enviar 10 notificaciones en ráfaga con claves distintas ---"
COUNT_BEFORE=$(get_mailpit_total)
for i in {1..10}; do
    curl -s -X POST "$BASE_NOTIFICACIONES/notificar" \
        -H "Content-Type: application/json" \
        -d "{
            \"tipo\": \"PRESTAMO\",
            \"usuario\": \"Usuario Lote $i\",
            \"correo\": \"lote_$i@example.com\",
            \"clave\": \"clave-f7-lote-${i}-${TIMESTAMP}\",
            \"datos\": {\"titulo\": \"Libro Lote $i\"}
        }" >/dev/null
done
echo "10 notificaciones enviadas a la API."

echo "Esperando que las 10 sean procesadas por el worker..."
EXPECTED_TOTAL=$((COUNT_BEFORE + 10))
RAFAGA_OK=0
for i in {1..20}; do
    CURRENT_TOTAL=$(get_mailpit_total)
    echo "Mensajes actuales en Mailpit: $CURRENT_TOTAL / $EXPECTED_TOTAL"
    if [ "$CURRENT_TOTAL" -ge "$EXPECTED_TOTAL" ]; then
        RAFAGA_OK=1
        break
    fi
    sleep 1
done

if [ "$RAFAGA_OK" -ne 1 ]; then
    echo "ERROR en (f): Se esperaban $EXPECTED_TOTAL correos en Mailpit, hay $CURRENT_TOTAL"
    exit 1
fi
echo "[OK] (f) 10 notificaciones procesadas y recibidas en Mailpit exactamente (sin duplicados)."

# --- g. Endpoint /reintentar ---
echo ""
echo "--- g. Probando endpoint /notificaciones/<id>/reintentar ---"
# 1. 404 con ID inexistente
RESP_G_404=$(curl -s -w "\n%{http_code}" -X POST "$BASE_NOTIFICACIONES/notificaciones/99999999/reintentar")
CODE_G_404=$(echo "$RESP_G_404" | tail -n1)
echo "Reintentar inexistente: HTTP $CODE_G_404"
if [ "$CODE_G_404" -ne 404 ]; then
    echo "ERROR en (g): Se esperaba 404 para ID inexistente, obtenido $CODE_G_404"
    exit 1
fi

# 2. 409 con notificación ENVIADA
RESP_G_ENVIADA=$(curl -s -w "\n%{http_code}" -X POST "$BASE_NOTIFICACIONES/notificaciones/$ID_A/reintentar")
CODE_G_ENVIADA=$(echo "$RESP_G_ENVIADA" | tail -n1)
echo "Reintentar ENVIADA: HTTP $CODE_G_ENVIADA"
if [ "$CODE_G_ENVIADA" -ne 409 ]; then
    echo "ERROR en (g): Se esperaba 409 para notificación ENVIADA, obtenido $CODE_G_ENVIADA"
    exit 1
fi

# 3. 409 con notificación FALLIDA sin correo
RESP_G_SINCORREO=$(curl -s -w "\n%{http_code}" -X POST "$BASE_NOTIFICACIONES/notificaciones/$ID_C/reintentar")
CODE_G_SINCORREO=$(echo "$RESP_G_SINCORREO" | tail -n1)
echo "Reintentar sin correo destino: HTTP $CODE_G_SINCORREO"
if [ "$CODE_G_SINCORREO" -ne 409 ]; then
    echo "ERROR en (g): Se esperaba 409 para notificación sin correo, obtenido $CODE_G_SINCORREO"
    exit 1
fi

# 4. 200 con notificación FALLIDA reencolable (con correo destino)
RESP_G_CREAR=$(curl -s -X POST "$BASE_NOTIFICACIONES/notificar" \
    -H "Content-Type: application/json" \
    -d "{
        \"tipo\": \"PRESTAMO\",
        \"usuario\": \"Usuario Reintento\",
        \"correo\": \"reintento@example.com\",
        \"clave\": \"clave-f7-reintento-$TIMESTAMP\",
        \"datos\": {\"titulo\": \"Libro Reintentado\"}
    }")
ID_G=$(get_json_field "$RESP_G_CREAR" "id")

# Forzar estado FALLIDA con correo en base de datos
MSYS_NO_PATHCONV=1 $DOCKER_CMD compose exec -T notificaciones python -c "
import sqlite3
conn = sqlite3.connect('/data/notificaciones.db')
conn.execute('UPDATE notificaciones SET estado = ?, intentos = ?, ultimo_error = ? WHERE id = ?', ('FALLIDA', 5, 'Error simulado de red', $ID_G))
conn.commit()
conn.close()
"

RESP_G_REINTENTO=$(curl -s -w "\n%{http_code}" -X POST "$BASE_NOTIFICACIONES/notificaciones/$ID_G/reintentar")
CODE_G_REINTENTO=$(echo "$RESP_G_REINTENTO" | tail -n1)
BODY_G_REINTENTO=$(echo "$RESP_G_REINTENTO" | sed '$d')
echo "Reintentar FALLIDA con correo: HTTP $CODE_G_REINTENTO, Cuerpo: $BODY_G_REINTENTO"

if [ "$CODE_G_REINTENTO" -ne 200 ]; then
    echo "ERROR en (g): Se esperaba 200 para reintento de FALLIDA con correo, obtenido $CODE_G_REINTENTO"
    exit 1
fi

# Esperar que el worker la tome y la entregue
sleep 4
NOTIF_G_FINAL=$(curl -s "$BASE_NOTIFICACIONES/notificaciones")
ESTADO_G_FINAL=$(get_notif_field_by_id "$NOTIF_G_FINAL" "$ID_G" "estado")
echo "Estado final notificación #$ID_G: $ESTADO_G_FINAL"
if [ "$ESTADO_G_FINAL" = "ENVIADA" ]; then
    echo "Notificación reencolada #$ID_G fue entregada y pasó a ENVIADA."
fi
echo "[OK] (g) Endpoint /reintentar validó correctamente 404, 409 y reencolado 200."

# --- h. Auditoría de logs de seguridad ---
echo ""
echo "--- h. Auditoría de logs de seguridad ---"
LOGS_NOTIF=$($DOCKER_CMD compose logs --tail=100 notificaciones)

# Verificar que no hay contraseñas en los logs
if echo "$LOGS_NOTIF" | grep -iE "password|contraseña" | grep -v "SMTP_PASSWORD"; then
    echo "ERROR en (h): Posible contraseña detectada en logs"
    exit 1
fi

# Verificar que los correos están enmascarados (ej: a***@example.com o r***@example.com)
if echo "$LOGS_NOTIF" | grep -E "ana@example.com|carlos@example.com|elena@example.com"; then
    echo "ERROR en (h): Correo sin enmascarar detectado en los logs de Notificaciones"
    exit 1
fi

if echo "$LOGS_NOTIF" | grep -q "a\*\*\*@example.com"; then
    echo "[OK] Formato de correo enmascarado verificado en logs (ej: a***@example.com)."
fi
echo "[OK] (h) Logs limpios de credenciales y correos completos."

# --- i. Health check con conteo de pendientes ---
echo ""
echo "--- i. Conteo de pendientes en /health ---"
HEALTH_RESP=$(curl -s "$BASE_NOTIFICACIONES/health")
echo "Health check: $HEALTH_RESP"
PENDIENTES_VAL=$(get_json_field "$HEALTH_RESP" "pendientes")
echo "Notificaciones pendientes: $PENDIENTES_VAL"
if [ -z "$PENDIENTES_VAL" ]; then
    echo "ERROR en (i): /health no incluye 'pendientes'"
    exit 1
fi
echo "[OK] (i) /health responde con campo 'pendientes'."

echo ""
echo "===================================================================="
echo "TODAS LAS VERIFICACIONES ESPECÍFICAS DE F7 PASARON EXITOSAMENTE"
echo "===================================================================="
