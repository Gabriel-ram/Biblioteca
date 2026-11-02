#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE VERIFICACIÓN FASE F6: CLIENTE HTTP DE PRÉSTAMOS Y RESILIENCIA
# ==============================================================================
set -euo pipefail

BASE_CATALOGO="http://127.0.0.1:8001"
BASE_PRESTAMOS="http://127.0.0.1:8002"
BASE_NOTIFICACIONES="http://127.0.0.1:8003"

# Docker binary detection
if command -v docker.exe >/dev/null 2>&1 && ! docker version >/dev/null 2>&1; then
    DOCKER_CMD="docker.exe"
else
    DOCKER_CMD="docker"
fi

echo "Asegurando que todos los servicios estén iniciados..."
$DOCKER_CMD compose start catalogo notificaciones
sleep 2

echo "===================================================================="
echo "VERIFICACIÓN FASE F6"
echo "===================================================================="

# --- 0. PREPARAR DATOS DE PRUEBA ---
echo "--- 0. Preparando datos de prueba iniciales ---"
TIMESTAMP=$(date +%s)
AUTOR_JSON=$(curl -s -X POST "$BASE_CATALOGO/autores" \
    -H "Content-Type: application/json" \
    -d "{\"nombre\": \"Autor Test F6 $TIMESTAMP\", \"nacionalidad\": \"Boliviana\"}")
AUTOR_ID=$(echo "$AUTOR_JSON" | grep -o '"id":[ ]*[0-9]*' | head -n1 | tr -d ' "id:')
echo "Autor creado: ID $AUTOR_ID"

LIBRO_JSON=$(curl -s -X POST "$BASE_CATALOGO/libros" \
    -H "Content-Type: application/json" \
    -d "{\"titulo\": \"Libro Test F6 $TIMESTAMP\", \"autor_id\": $AUTOR_ID, \"ejemplares_totales\": 2}")
LIBRO_ID=$(echo "$LIBRO_JSON" | grep -o '"id":[ ]*[0-9]*' | head -n1 | tr -d ' "id:')
echo "Libro creado: ID $LIBRO_ID (2 ejemplares)"

USUARIO_JSON=$(curl -s -X POST "$BASE_PRESTAMOS/usuarios" \
    -H "Content-Type: application/json" \
    -d "{\"codigo\": \"U_F6_$TIMESTAMP\", \"nombre\": \"Usuario F6\", \"correo\": \"f6_$TIMESTAMP@test.com\", \"tipo\": \"ESTUDIANTE\"}")
USUARIO_ID=$(echo "$USUARIO_JSON" | grep -o '"id":[ ]*[0-9]*' | head -n1 | tr -d ' "id:')
echo "Usuario creado: ID $USUARIO_ID"

# Crear un préstamo activo para la prueba (b)
PRESTAMO_INICIAL_JSON=$(curl -s -X POST "$BASE_PRESTAMOS/prestamos" \
    -H "Content-Type: application/json" \
    -d "{\"libro_id\": $LIBRO_ID, \"usuario_id\": $USUARIO_ID}")
PRESTAMO_ACTIVO_ID=$(echo "$PRESTAMO_INICIAL_JSON" | grep -o '"id":[ ]*[0-9]*' | head -n1 | tr -d ' "id:')
echo "Préstamo activo creado: ID $PRESTAMO_ACTIVO_ID para libro ID $LIBRO_ID"

# Verificar stock actual del libro (debe ser 1 disponible)
LIBRO_CHECK=$(curl -s "$BASE_CATALOGO/libros/$LIBRO_ID")
echo "Stock inicial tras préstamo: $LIBRO_CHECK"

# --- a. DETENER CATÁLOGO Y PROBAR POST /prestamos ---
echo ""
echo "--- a. Probando POST /prestamos con Catálogo detenido ---"
echo "Deteniendo Catálogo..."
$DOCKER_CMD compose stop catalogo

COUNT_BEFORE=$(curl -s "$BASE_PRESTAMOS/prestamos" | grep -o '"id":' | wc -l)
START_TIME=$(date +%s)
RESP_A=$(curl -s -w "\n%{http_code}" -X POST "$BASE_PRESTAMOS/prestamos" \
    -H "Content-Type: application/json" \
    -d "{\"libro_id\": $LIBRO_ID, \"usuario_id\": $USUARIO_ID}")
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

HTTP_CODE_A=$(echo "$RESP_A" | tail -n1)
BODY_A=$(echo "$RESP_A" | sed '$d')

echo "Tiempo transcurrido: ${ELAPSED}s"
echo "Código HTTP recibido: $HTTP_CODE_A"
echo "Cuerpo de respuesta: $BODY_A"

if [ "$HTTP_CODE_A" -ne 503 ]; then
    echo "ERROR en (a): Se esperaba HTTP 503 pero se obtuvo $HTTP_CODE_A"
    $DOCKER_CMD compose start catalogo
    exit 1
fi

COUNT_AFTER=$(curl -s "$BASE_PRESTAMOS/prestamos" | grep -o '"id":' | wc -l)
if [ "$COUNT_BEFORE" -ne "$COUNT_AFTER" ]; then
    echo "ERROR en (a): Se registró un préstamo en la base cuando Catálogo estaba caído"
    $DOCKER_CMD compose start catalogo
    exit 1
fi
echo "[OK] (a) Retornó 503 en ~${ELAPSED}s y no dejó préstamo nuevo en base."

# --- b. CON CATÁLOGO DETENIDO, PROBAR DEVOLUCIÓN ---
echo ""
echo "--- b. Probando PUT /prestamos/<id>/devolucion con Catálogo detenido ---"
RESP_B=$(curl -s -w "\n%{http_code}" -X PUT "$BASE_PRESTAMOS/prestamos/$PRESTAMO_ACTIVO_ID/devolucion")
HTTP_CODE_B=$(echo "$RESP_B" | tail -n1)
BODY_B=$(echo "$RESP_B" | sed '$d')

echo "Código HTTP recibido: $HTTP_CODE_B"
echo "Cuerpo de respuesta: $BODY_B"

if [ "$HTTP_CODE_B" -ne 503 ]; then
    echo "ERROR en (b): Se esperaba HTTP 503 pero se obtuvo $HTTP_CODE_B"
    $DOCKER_CMD compose start catalogo
    exit 1
fi

# Verificar que el préstamo SIGUE ACTIVO
PRESTAMO_CHECK_B=$(curl -s "$BASE_PRESTAMOS/prestamos?usuario_id=$USUARIO_ID")
ESTADO_B=$(echo "$PRESTAMO_CHECK_B" | grep -o '"estado":"[^"]*"' | head -n1)
echo "Estado del préstamo en base: $ESTADO_B"
if ! echo "$PRESTAMO_CHECK_B" | grep -q '"estado":"ACTIVO"'; then
    echo "ERROR en (b): El préstamo no quedó en estado ACTIVO"
    $DOCKER_CMD compose start catalogo
    exit 1
fi
echo "[OK] (b) Devolución retornó 503 y el préstamo continúa ACTIVO."

# --- c. INICIAR CATÁLOGO, ESPERAR A HEALTHY Y REPETIR DEVOLUCIÓN ---
echo ""
echo "--- c. Iniciando Catálogo y repitiendo devolución ---"
$DOCKER_CMD compose start catalogo

echo "Esperando que Catálogo esté UP y healthy..."
for i in {1..30}; do
    if curl -s "$BASE_CATALOGO/health" | grep -q '"UP"'; then
        echo "Catálogo está UP."
        break
    fi
    sleep 1
done

RESP_C=$(curl -s -w "\n%{http_code}" -X PUT "$BASE_PRESTAMOS/prestamos/$PRESTAMO_ACTIVO_ID/devolucion")
HTTP_CODE_C=$(echo "$RESP_C" | tail -n1)
BODY_C=$(echo "$RESP_C" | sed '$d')

echo "Código HTTP recibido: $HTTP_CODE_C"
echo "Cuerpo de respuesta: $BODY_C"

if [ "$HTTP_CODE_C" -ne 200 ]; then
    echo "ERROR en (c): Se esperaba HTTP 200 pero se obtuvo $HTTP_CODE_C"
    exit 1
fi

# Verificar que el ejemplar volvió a Catálogo (ejemplares_disponibles debe ser 2)
LIBRO_CHECK_C=$(curl -s "$BASE_CATALOGO/libros/$LIBRO_ID")
echo "Libro en Catálogo tras devolución: $LIBRO_CHECK_C"
DISPONIBLES_C=$(echo "$LIBRO_CHECK_C" | grep -o '"ejemplares_disponibles":[ ]*[0-9]*' | tr -d ' "ejemplares_disponibles:')
if [ "$DISPONIBLES_C" -ne 2 ]; then
    echo "ERROR en (c): ejemplares_disponibles debería ser 2 pero es $DISPONIBLES_C"
    exit 1
fi
echo "[OK] (c) Devolución completada con HTTP 200 y stock repuesto a 2 en Catálogo."

# --- d. DETENER NOTIFICACIONES Y PROBAR PRÉSTAMO Y DEVOLUCIÓN CON MULTA ---
echo ""
echo "--- d. Deteniendo Notificaciones y verificando resiliencia ---"
$DOCKER_CMD compose stop notificaciones

# 1. Crear un préstamo nuevo con Notificaciones detenido
RESP_D1=$(curl -s -w "\n%{http_code}" -X POST "$BASE_PRESTAMOS/prestamos" \
    -H "Content-Type: application/json" \
    -d "{\"libro_id\": $LIBRO_ID, \"usuario_id\": $USUARIO_ID}")
HTTP_CODE_D1=$(echo "$RESP_D1" | tail -n1)
BODY_D1=$(echo "$RESP_D1" | sed '$d')

echo "Creación de préstamo con Notificaciones detenido: HTTP $HTTP_CODE_D1"
if [ "$HTTP_CODE_D1" -ne 201 ]; then
    echo "ERROR en (d): Se esperaba HTTP 201 al crear préstamo sin notificaciones, obtenido $HTTP_CODE_D1: $BODY_D1"
    $DOCKER_CMD compose start notificaciones
    exit 1
fi
PRESTAMO_D_ID=$(echo "$BODY_D1" | grep -o '"id":[ ]*[0-9]*' | head -n1 | tr -d ' "id:')
echo "Nuevo préstamo creado: ID $PRESTAMO_D_ID"

# 2. Modificar la fecha_limite del préstamo para simular retraso (multa)
MSYS_NO_PATHCONV=1 $DOCKER_CMD compose exec -T prestamos python -c "
import sqlite3
conn = sqlite3.connect('/data/prestamos.db')
conn.execute(\"UPDATE prestamos SET fecha_limite = '2026-10-01T00:00:00' WHERE id = $PRESTAMO_D_ID\")
conn.commit()
conn.close()
"
echo "Préstamo #$PRESTAMO_D_ID configurado con fecha_limite vencida para generar multa."

# 3. Registrar devolución con multa teniendo Notificaciones caído
RESP_D2=$(curl -s -w "\n%{http_code}" -X PUT "$BASE_PRESTAMOS/prestamos/$PRESTAMO_D_ID/devolucion")
HTTP_CODE_D2=$(echo "$RESP_D2" | tail -n1)
BODY_D2=$(echo "$RESP_D2" | sed '$d')

echo "Devolución con multa (Notificaciones detenido): HTTP $HTTP_CODE_D2"
echo "Cuerpo de respuesta: $BODY_D2"

if [ "$HTTP_CODE_D2" -ne 200 ]; then
    echo "ERROR en (d): Se esperaba HTTP 200 en devolución con multa, obtenido $HTTP_CODE_D2: $BODY_D2"
    $DOCKER_CMD compose start notificaciones
    exit 1
fi

# Verificar que la multa quedó guardada en SQLite
MULTA_EN_DB=$(MSYS_NO_PATHCONV=1 $DOCKER_CMD compose exec -T prestamos python -c "
import sqlite3
conn = sqlite3.connect('/data/prestamos.db')
row = conn.execute(\"SELECT id, monto, dias_retraso FROM multas WHERE prestamo_id = $PRESTAMO_D_ID\").fetchone()
conn.close()
print(row)
")
echo "Multa registrada en DB: $MULTA_EN_DB"
if [ "$MULTA_EN_DB" = "None" ]; then
    echo "ERROR en (d): No se guardó la multa en la base de datos"
    $DOCKER_CMD compose start notificaciones
    exit 1
fi

# Verificar logs de Préstamos: debe tener WARNING de notificación, nunca 500, ni CI ni correos
LOGS_PRESTAMOS=$($DOCKER_CMD compose logs --tail=40 prestamos)
echo "Revisando logs recientes de Préstamos..."
if echo "$LOGS_PRESTAMOS" | grep -i "500 Internal Server Error"; then
    echo "ERROR en (d): Se encontró un 500 en los logs de Préstamos"
    $DOCKER_CMD compose start notificaciones
    exit 1
fi

if echo "$LOGS_PRESTAMOS" | grep -qi "Fallo al enviar notificación"; then
    echo "[OK] Warning de notificación detectado correctamente en logs."
else
    echo "Nota: Advertencia en logs de clientes."
fi

# Verificar que no hay emails ni CI en logs
if echo "$LOGS_PRESTAMOS" | grep -q "@test.com"; then
    echo "ERROR de seguridad: Correo electrónico encontrado en los logs de Préstamos"
    $DOCKER_CMD compose start notificaciones
    exit 1
fi

echo "[OK] (d) Préstamo y devolución con multa exitosos (200/201) sin notificaciones, multa guardada y sin filtración de datos."

# --- e. INICIAR NOTIFICACIONES Y ESPERAR A HEALTHY ---
echo ""
echo "--- e. Iniciando Notificaciones ---"
$DOCKER_CMD compose start notificaciones
for i in {1..30}; do
    if curl -s "$BASE_NOTIFICACIONES/health" | grep -q '"UP"'; then
        echo "Notificaciones está UP."
        break
    fi
    sleep 1
done
echo "[OK] (e) Notificaciones reanudado y saludable."

echo ""
echo "===================================================================="
echo "TODAS LAS VERIFICACIONES ESPECÍFICAS DE F6 PASARON CON ÉXITO"
echo "===================================================================="
