#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE PRUEBA DE CONCURRENCIA - CATALOGO (FASE F3)
# ==============================================================================
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"

echo "===================================================================="
echo "Iniciando prueba de concurrencia contra $BASE_URL"
echo "===================================================================="

TIMESTAMP=$(date +%s%N 2>/dev/null || date +%s)
AUTOR_NOMBRE="Autor Concurrencia ${TIMESTAMP}_${RANDOM}"
LIBRO_TITULO="Libro Concurrencia ${TIMESTAMP}_${RANDOM}"

# 1. Crear Autor
echo "1. Creando autor con nombre único: '$AUTOR_NOMBRE'..."
RESP_AUTOR=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/autores" \
    -H "Content-Type: application/json" \
    -d "{\"nombre\": \"$AUTOR_NOMBRE\", \"nacionalidad\": \"Test\"}")

HTTP_AUTOR=$(echo "$RESP_AUTOR" | tail -n1)
BODY_AUTOR=$(echo "$RESP_AUTOR" | sed '$d')

if [ "$HTTP_AUTOR" -ne 201 ] && [ "$HTTP_AUTOR" -ne 200 ]; then
    echo "ERROR al crear autor: HTTP $HTTP_AUTOR - $BODY_AUTOR"
    exit 1
fi

AUTOR_ID=$(echo "$BODY_AUTOR" | grep -o '"id":[ ]*[0-9]*' | head -n1 | tr -d ' "id:')
if [ -z "$AUTOR_ID" ]; then
    echo "ERROR: No se pudo obtener AUTOR_ID de la respuesta: $BODY_AUTOR"
    exit 1
fi
echo "Autor creado con ID: $AUTOR_ID"

# 2. Crear Libro con 3 ejemplares
echo "2. Creando libro con 3 ejemplares disponibles: '$LIBRO_TITULO'..."
RESP_LIBRO=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/libros" \
    -H "Content-Type: application/json" \
    -d "{\"titulo\": \"$LIBRO_TITULO\", \"autor_id\": $AUTOR_ID, \"ejemplares_totales\": 3}")

HTTP_LIBRO=$(echo "$RESP_LIBRO" | tail -n1)
BODY_LIBRO=$(echo "$RESP_LIBRO" | sed '$d')

if [ "$HTTP_LIBRO" -ne 201 ]; then
    echo "ERROR al crear libro: HTTP $HTTP_LIBRO - $BODY_LIBRO"
    exit 1
fi

LIBRO_ID=$(echo "$BODY_LIBRO" | grep -o '"id":[ ]*[0-9]*' | head -n1 | tr -d ' "id:')
if [ -z "$LIBRO_ID" ]; then
    echo "ERROR: No se pudo obtener LIBRO_ID de la respuesta: $BODY_LIBRO"
    exit 1
fi
echo "Libro creado con ID: $LIBRO_ID (ejemplares_totales: 3, ejemplares_disponibles: 3)"

# 3. Lanzar 20 peticiones concurrentes PATCH descontar
echo "3. Lanzando 20 peticiones concurrentes PATCH 'descontar'..."
TMP_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t 'concurr')
trap 'rm -rf "$TMP_DIR"' EXIT

for i in $(seq 1 20); do
    (
        CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "${BASE_URL}/libros/${LIBRO_ID}/disponibilidad" \
            -H "Content-Type: application/json" \
            -d '{"operacion": "descontar"}')
        echo "$CODE" > "$TMP_DIR/res_$i.txt"
    ) &
done

wait

cat "$TMP_DIR"/res_*.txt > "$TMP_DIR/todos_codigos.txt"

C200=$(grep -c "^200$" "$TMP_DIR/todos_codigos.txt" || true)
C409=$(grep -c "^409$" "$TMP_DIR/todos_codigos.txt" || true)
C500=$(grep -c "^500$" "$TMP_DIR/todos_codigos.txt" || true)
TOTAL=$(wc -l < "$TMP_DIR/todos_codigos.txt" | tr -d ' ')

echo "Resultados de las 20 peticiones concurrentes:"
echo " - HTTP 200 (éxito al descontar): $C200"
echo " - HTTP 409 (stock agotado):      $C409"
echo " - HTTP 500 (error interno):       $C500"
echo " - Total procesadas:              $TOTAL"

EXIT_CODE=0

if [ "$C200" -ne 3 ]; then
    echo "FALLO: Se esperaban exactamente 3 respuestas HTTP 200, obtenidas: $C200"
    EXIT_CODE=1
fi

if [ "$C409" -ne 17 ]; then
    echo "FALLO: Se esperaban exactamente 17 respuestas HTTP 409, obtenidas: $C409"
    EXIT_CODE=1
fi

if [ "$C500" -ne 0 ]; then
    echo "FALLO: Se obtuvieron $C500 respuestas HTTP 500."
    EXIT_CODE=1
fi

# 4. Verificar estado final del libro
echo "4. Verificando estado final del libro (GET /libros/$LIBRO_ID)..."
FINAL_LIBRO=$(curl -s -X GET "${BASE_URL}/libros/${LIBRO_ID}")
echo "Libro final: $FINAL_LIBRO"

DISPONIBLES=$(echo "$FINAL_LIBRO" | grep -o '"ejemplares_disponibles":[ ]*[0-9]*' | head -n1 | tr -d ' "ejemplares_disponibles:')

if [ "$DISPONIBLES" != "0" ]; then
    echo "FALLO: Se esperaba ejemplares_disponibles = 0, obtenido: '$DISPONIBLES'."
    EXIT_CODE=1
else
    echo "OK: ejemplares_disponibles es exactamente 0."
fi

# 5. Verificar logs por 'database is locked' o errores en catalogo
echo "5. Verificando logs del servicio catalogo..."
if command -v docker.exe >/dev/null 2>&1 && ! docker version >/dev/null 2>&1; then
    DOCKER_CMD="docker.exe"
else
    DOCKER_CMD="docker"
fi

LOGS=$($DOCKER_CMD logs catalogo_service 2>&1 || $DOCKER_CMD compose logs catalogo 2>&1 || true)
if echo "$LOGS" | grep -qi "database is locked"; then
    echo "FALLO: 'database is locked' encontrado en logs del contenedor."
    EXIT_CODE=1
else
    echo "OK: No se encontró 'database is locked' en los logs."
fi

if [ "$EXIT_CODE" -eq 0 ]; then
    echo "===================================================================="
    echo "PRUEBA DE CONCURRENCIA COMPLETADA CON ÉXITO (Todos los checks OK)"
    echo "===================================================================="
    exit 0
else
    echo "===================================================================="
    echo "PRUEBA DE CONCURRENCIA FINALIZÓ CON ERRORES"
    echo "===================================================================="
    exit 1
fi

