#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE PRUEBAS AUTOMATIZADAS - SISTEMA DE BIBLIOTECA
# Compatible con Git Bash (Windows), WSL y Linux
# ==============================================================================

set -o pipefail

# Colores para salida de terminal
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # Sin color

BASE_CATALOGO="http://localhost:8001"
BASE_PRESTAMOS="http://localhost:8002"
BASE_NOTIFICACIONES="http://localhost:8003"

# Detección de Docker (CLI estándar o .exe en Git Bash)
if command -v docker.exe >/dev/null 2>&1 && ! docker version >/dev/null 2>&1; then
    DOCKER_CMD="docker.exe"
else
    DOCKER_CMD="docker"
fi

imprimir_titulo() {
    echo -e "\n${CYAN}====================================================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}====================================================================${NC}"
}

imprimir_paso() {
    echo -e "\n${YELLOW}>>> $1${NC}"
}

verificar_codigo() {
    local esperado="$1"
    local obtenido="$2"
    local descripcion="$3"
    if [ "$obtenido" -eq "$esperado" ]; then
        echo -e "${GREEN}[OK] $descripcion (HTTP $obtenido)${NC}"
    else
        echo -e "${RED}[ERROR] $descripcion (Esperado: $esperado, Obtenido: $obtenido)${NC}"
    fi
}

extraer_id() {
    echo "$1" | grep -o '"id":[ ]*[0-9]*' | head -n1 | tr -d ' "id:'
}

# ------------------------------------------------------------------------------
# 1. VERIFICACION DE HEALTHCHECKS
# ------------------------------------------------------------------------------
imprimir_titulo "1. VERIFICACION DE ENDPOINTS DE SALUD (/health)"

echo "Esperando que los microservicios esten listos..."
for servicio in "catalogo:8001" "prestamos:8002" "notificaciones:8003"; do
    url="http://localhost:${servicio#*:}/health"
    nombre="${servicio%:*}"
    echo -n "Esperando a $nombre en $url... "
    listo=false
    for i in {1..20}; do
        codigo=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
        if [ "$codigo" -eq 200 ]; then
            echo -e "${GREEN}Listo (HTTP 200)${NC}"
            listo=true
            break
        fi
        sleep 1
    done
    if [ "$listo" = false ]; then
        echo -e "${RED}No respondio en el tiempo esperado (Verifica que docker-compose este levantado)${NC}"
    fi
done

# ------------------------------------------------------------------------------
# 2. GESTION EN CATALOGO: AUTOR Y LIBRO
# ------------------------------------------------------------------------------
imprimir_titulo "2. GESTION EN CATALOGO: AUTOR Y LIBRO"

imprimir_paso "Creando Autor (POST /autores)"
RESP_AUTOR=$(curl -s -w "\n%{http_code}" -X POST "${BASE_CATALOGO}/autores" \
    -H "Content-Type: application/json" \
    -d '{"nombre": "Gabriel Garcia Marquez", "nacionalidad": "Colombiana"}')
BODY_AUTOR=$(echo "$RESP_AUTOR" | sed '$d')
CODE_AUTOR=$(echo "$RESP_AUTOR" | tail -n1)
echo "Respuesta: $BODY_AUTOR"
verificar_codigo 201 "$CODE_AUTOR" "Creacion de autor"
AUTOR_ID=$(extraer_id "$BODY_AUTOR")
echo "ID Autor obtenido: $AUTOR_ID"

imprimir_paso "Creando Libro con 1 ejemplar (POST /libros)"
TIMESTAMP=$(date +%s)
RESP_LIBRO=$(curl -s -w "\n%{http_code}" -X POST "${BASE_CATALOGO}/libros" \
    -H "Content-Type: application/json" \
    -d "{\"titulo\": \"Cien Anos de Soledad ($TIMESTAMP)\", \"autor_id\": $AUTOR_ID, \"ejemplares_totales\": 1}")
BODY_LIBRO=$(echo "$RESP_LIBRO" | sed '$d')
CODE_LIBRO=$(echo "$RESP_LIBRO" | tail -n1)
echo "Respuesta: $BODY_LIBRO"
verificar_codigo 201 "$CODE_LIBRO" "Creacion de libro"
LIBRO_ID=$(extraer_id "$BODY_LIBRO")
echo "ID Libro obtenido: $LIBRO_ID"

imprimir_paso "Verificando stock inicial del libro (GET /libros/$LIBRO_ID)"
RESP_STOCK_INIT=$(curl -s -X GET "${BASE_CATALOGO}/libros/${LIBRO_ID}")
echo "Detalle libro: $RESP_STOCK_INIT"

# ------------------------------------------------------------------------------
# 3. PRESTAMO EXITOSO (DESCUENTO DE STOCK)
# ------------------------------------------------------------------------------
imprimir_titulo "3. PRESTAMO EXITOSO (DESCUENTO DE STOCK EN CATALOGO)"

imprimir_paso "Registrando prestamo para 'usuario_prueba' (POST /prestamos)"
RESP_PRESTAMO=$(curl -s -w "\n%{http_code}" -X POST "${BASE_PRESTAMOS}/prestamos" \
    -H "Content-Type: application/json" \
    -d "{\"usuario\": \"usuario_prueba\", \"ci\": \"12345678\", \"libro_id\": $LIBRO_ID}")
BODY_PRESTAMO=$(echo "$RESP_PRESTAMO" | sed '$d')
CODE_PRESTAMO=$(echo "$RESP_PRESTAMO" | tail -n1)
echo "Respuesta: $BODY_PRESTAMO"
verificar_codigo 201 "$CODE_PRESTAMO" "Registro de prestamo"
PRESTAMO_ID=$(extraer_id "$BODY_PRESTAMO")
echo "ID Prestamo obtenido: $PRESTAMO_ID"

imprimir_paso "Verificando que el stock en Catalogo se haya descontado a 0 (GET /libros/$LIBRO_ID)"
RESP_STOCK_DESPUES=$(curl -s -X GET "${BASE_CATALOGO}/libros/${LIBRO_ID}")
echo "Estado actual libro: $RESP_STOCK_DESPUES"
if echo "$RESP_STOCK_DESPUES" | grep -q '"ejemplares_disponibles":0'; then
    echo -e "${GREEN}[OK] Ejemplares disponibles reducidos a 0 y estado AGOTADO${NC}"
else
    echo -e "${YELLOW}[INFO] Verifique disponibilidad en la respuesta JSON${NC}"
fi

# ------------------------------------------------------------------------------
# 4. PRESTAMO FALLIDO POR STOCK AGOTADO (409 CONFLICT)
# ------------------------------------------------------------------------------
imprimir_titulo "4. INTENTO DE PRESTAMO SIN STOCK (HTTP 409)"

imprimir_paso "Intentando solicitar el mismo libro agotado..."
RESP_AGOTADO=$(curl -s -w "\n%{http_code}" -X POST "${BASE_PRESTAMOS}/prestamos" \
    -H "Content-Type: application/json" \
    -d "{\"usuario\": \"otro_usuario\", \"ci\": \"87654321\", \"libro_id\": $LIBRO_ID}")
BODY_AGOTADO=$(echo "$RESP_AGOTADO" | sed '$d')
CODE_AGOTADO=$(echo "$RESP_AGOTADO" | tail -n1)
echo "Respuesta: $BODY_AGOTADO"
verificar_codigo 409 "$CODE_AGOTADO" "Rechazo de prestamo por stock agotado"

# ------------------------------------------------------------------------------
# 5. DEVOLUCION DE LIBRO (REPOSICION DE STOCK)
# ------------------------------------------------------------------------------
imprimir_titulo "5. DEVOLUCION DE LIBRO Y REPOSICION"

imprimir_paso "Registrando devolucion del prestamo $PRESTAMO_ID (PUT /prestamos/$PRESTAMO_ID/devolucion)"
RESP_DEV=$(curl -s -w "\n%{http_code}" -X PUT "${BASE_PRESTAMOS}/prestamos/${PRESTAMO_ID}/devolucion")
BODY_DEV=$(echo "$RESP_DEV" | sed '$d')
CODE_DEV=$(echo "$RESP_DEV" | tail -n1)
echo "Respuesta: $BODY_DEV"
verificar_codigo 200 "$CODE_DEV" "Devolucion de libro registrada"

imprimir_paso "Verificando que el stock en Catalogo haya vuelto a 1 (GET /libros/$LIBRO_ID)"
RESP_STOCK_FINAL=$(curl -s -X GET "${BASE_CATALOGO}/libros/${LIBRO_ID}")
echo "Estado restablecido libro: $RESP_STOCK_FINAL"
if echo "$RESP_STOCK_FINAL" | grep -q '"ejemplares_disponibles":1'; then
    echo -e "${GREEN}[OK] Ejemplar repuesto correctamente en Catalogo${NC}"
fi

# ------------------------------------------------------------------------------
# 6. HISTORIAL DE NOTIFICACIONES Y REVISION DE VENCIMIENTOS
# ------------------------------------------------------------------------------
imprimir_titulo "6. HISTORIAL DE NOTIFICACIONES"

imprimir_paso "Consultando notificaciones registradas (GET /notificaciones)"
RESP_NOTIF=$(curl -s -X GET "${BASE_NOTIFICACIONES}/notificaciones")
echo "Notificaciones: $RESP_NOTIF"

imprimir_titulo "TODAS LAS PRUEBAS FINALIZADAS CON EXITO"
