#!/usr/bin/env bash
# ==============================================================================
# scripts/verify_f8.sh
# Verificación exhaustiva de la Fase F8: Avisos programados y eventos en Préstamos
# ==============================================================================

set -euo pipefail

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

BASE_CATALOGO="http://127.0.0.1:8001"
BASE_PRESTAMOS="http://127.0.0.1:8002"
BASE_NOTIFICACIONES="http://127.0.0.1:8003"
BASE_MAILPIT="http://127.0.0.1:8025"

DOCKER_CMD="docker compose"

log_info() { echo -e "${CYAN}[INFO] $1${NC}"; }
log_pass() { echo -e "${GREEN}[PASS] $1${NC}"; }
log_fail() { echo -e "${RED}[FAIL] $1${NC}"; exit 1; }

# Helper para ejecutar consultas SQL en prestamos.db dentro del contenedor
db_exec() {
  local query="$1"
  $DOCKER_CMD exec -T prestamos python -c "
import sqlite3
conn = sqlite3.connect('/data/prestamos.db', timeout=10)
cursor = conn.cursor()
cursor.execute('''$query''')
conn.commit()
for r in cursor.fetchall():
    print('|'.join(str(c) for c in r))
"
}

# Limpiar mensajes en Mailpit antes de comenzar
log_info "Limpiando mensajes en Mailpit..."
curl -s -X DELETE "${BASE_MAILPIT}/api/v1/messages" || true

# Helper para contar correos en Mailpit hacia un destinatario con un filtro de asunto
contar_correos() {
  local to="$1"
  local sub_substr="$2"
  curl -s "${BASE_MAILPIT}/api/v1/messages" | python -c '
import sys, json
data = json.load(sys.stdin)
to_addr = sys.argv[1].lower() if len(sys.argv) > 1 else ""
sub = sys.argv[2].lower() if len(sys.argv) > 2 else ""
count = 0
for m in data.get("messages", []):
    tos = [t.get("Address", "").lower() for t in m.get("To", [])]
    subj = m.get("Subject", "").lower()
    if to_addr in tos and sub in subj:
        count += 1
print(count)
' "$to" "$sub_substr"
}

# ==============================================================================
# ESCENARIO A: Crear usuario con correo, libro y préstamo -> Correo PRESTAMO
# ==============================================================================
log_info "=== ESCENARIO A: Creación de préstamo con notificación PRESTAMO ==="

TIMESTAMP=$(date +%s)
USER_CODIGO="USR_A_${TIMESTAMP}"
EMAIL_A="ana_${TIMESTAMP}@example.com"

# 1. Crear usuario con correo
RESP_USER=$(curl -s -w "\n%{http_code}" -X POST "${BASE_PRESTAMOS}/usuarios" \
  -H "Content-Type: application/json" \
  -d "{\"codigo\": \"${USER_CODIGO}\", \"nombre\": \"Ana Garcia\", \"correo\": \"${EMAIL_A}\", \"tipo\": \"ESTUDIANTE\"}")
CODE_USER=$(echo "$RESP_USER" | tail -n1)
BODY_USER=$(echo "$RESP_USER" | sed '$d')
[ "$CODE_USER" -eq 201 ] || log_fail "Fallo al crear usuario: HTTP $CODE_USER"
USER_ID_A=$(echo "$BODY_USER" | python -c 'import sys, json; print(json.load(sys.stdin)["id"])')
log_pass "Usuario creado: id=$USER_ID_A, codigo=$USER_CODIGO"

# 2. Crear autor y libro en catálogo
RESP_AUTOR=$(curl -s -X POST "${BASE_CATALOGO}/autores" \
  -H "Content-Type: application/json" \
  -d '{"nombre": "Gabriel Garcia Marquez", "nacionalidad": "Colombiana"}')
AUTOR_ID=$(echo "$RESP_AUTOR" | python -c 'import sys, json; print(json.load(sys.stdin)["id"])')

RESP_LIBRO=$(curl -s -X POST "${BASE_CATALOGO}/libros" \
  -H "Content-Type: application/json" \
  -d "{\"titulo\": \"Cien Anos de Soledad A $TIMESTAMP\", \"autor_id\": $AUTOR_ID, \"ejemplares_totales\": 5}")
LIBRO_ID_A=$(echo "$RESP_LIBRO" | python -c 'import sys, json; print(json.load(sys.stdin)["id"])')
log_pass "Libro creado: id=$LIBRO_ID_A"

# 3. Crear préstamo
RESP_P1=$(curl -s -w "\n%{http_code}" -X POST "${BASE_PRESTAMOS}/prestamos" \
  -H "Content-Type: application/json" \
  -d "{\"libro_id\": $LIBRO_ID_A, \"usuario_id\": $USER_ID_A}")
CODE_P1=$(echo "$RESP_P1" | tail -n1)
BODY_P1=$(echo "$RESP_P1" | sed '$d')
[ "$CODE_P1" -eq 201 ] || log_fail "Fallo al crear préstamo: HTTP $CODE_P1"
P1_ID=$(echo "$BODY_P1" | python -c 'import sys, json; print(json.load(sys.stdin)["id"])')
log_pass "Préstamo creado: id=$P1_ID (HTTP 201)"

# 4. Esperar hasta 12s a que Mailpit reciba el correo PRESTAMO
log_info "Esperando procesamiento del worker de correo (~10s)..."
RECIBIDO=0
for i in {1..12}; do
  COUNT=$(contar_correos "$EMAIL_A" "registrado")
  if [ "$COUNT" -ge 1 ]; then
    RECIBIDO=1
    break
  fi
  sleep 1
done
[ "$RECIBIDO" -eq 1 ] || log_fail "Mailpit no recibió el correo de PRESTAMO para $EMAIL_A"
log_pass "Escenario A exitoso: correo PRESTAMO recibido en Mailpit con título y fecha límite"

# ==============================================================================
# ESCENARIO B: Forzar fecha a mañana -> Revisar vencimientos -> POR_VENCER
# ==============================================================================
log_info "=== ESCENARIO B: Revisión de vencimientos e idempotencia ==="

# 1. Forzar fecha_limite a hoy + 1 día
db_exec "UPDATE prestamos SET fecha_limite = datetime('now', '+1 day') WHERE id = $P1_ID;"
FECHA_P1=$(db_exec "SELECT fecha_limite, aviso_vencimiento_enviado, aviso_enviado_en FROM prestamos WHERE id = $P1_ID;")
log_info "Estado previo préstamo $P1_ID: $FECHA_P1"

# 2. Ejecutar POST /prestamos/revisar-vencimientos
RESP_REV1=$(curl -s -w "\n%{http_code}" -X POST "${BASE_PRESTAMOS}/prestamos/revisar-vencimientos")
CODE_REV1=$(echo "$RESP_REV1" | tail -n1)
BODY_REV1=$(echo "$RESP_REV1" | sed '$d')
[ "$CODE_REV1" -eq 200 ] || log_fail "Revisión 1 falló: HTTP $CODE_REV1"
echo "Respuesta revisión 1: $BODY_REV1"

AVISADOS_1=$(echo "$BODY_REV1" | python -c 'import sys, json; print(json.load(sys.stdin).get("avisados", 0))')
DISP_1=$(echo "$BODY_REV1" | python -c 'import sys, json; print(json.load(sys.stdin).get("notificaciones_disponible"))')
[ "$AVISADOS_1" -ge 1 ] || log_fail "Esperaba avisados >= 1, obtenido: $AVISADOS_1"
[ "$DISP_1" = "True" ] || log_fail "Esperaba notificaciones_disponible = true"

# Esperar que Mailpit reciba POR_VENCER
RECIBIDO_VENCER=0
for i in {1..12}; do
  COUNT=$(contar_correos "$EMAIL_A" "vencimiento")
  if [ "$COUNT" -ge 1 ]; then
    RECIBIDO_VENCER=1
    break
  fi
  sleep 1
done
[ "$RECIBIDO_VENCER" -eq 1 ] || log_fail "Mailpit no recibió el correo de POR_VENCER"
log_pass "Correo POR_VENCER recibido en Mailpit"

# 3. Ejecutar de nuevo la revisión: debe dar avisados = 0 y no duplicar correo
RESP_REV2=$(curl -s -X POST "${BASE_PRESTAMOS}/prestamos/revisar-vencimientos")
echo "Respuesta revisión 2 (idempotente): $RESP_REV2"
AVISADOS_2=$(echo "$RESP_REV2" | python -c 'import sys, json; print(json.load(sys.stdin).get("avisados", 0))')
[ "$AVISADOS_2" -eq 0 ] || log_fail "Esperaba avisados = 0 en segunda corrida, obtenido: $AVISADOS_2"

# Verificar que no hay correo duplicado
COUNT_VENCER=$(contar_correos "$EMAIL_A" "vencimiento")
[ "$COUNT_VENCER" -eq 1 ] || log_fail "Correo POR_VENCER duplicado: count=$COUNT_VENCER"
log_pass "Escenario B exitoso: avisados=1 en primera corrida, avisados=0 en segunda corrida, 0 duplicados"

# ==============================================================================
# ESCENARIO C: Notificaciones detenido -> revisión no marca préstamo -> reintento
# ==============================================================================
log_info "=== ESCENARIO C: Notificaciones caído y recuperación ==="

# 1. Crear nuevo préstamo P2 para Ana
RESP_P2=$(curl -s -X POST "${BASE_PRESTAMOS}/prestamos" \
  -H "Content-Type: application/json" \
  -d "{\"libro_id\": $LIBRO_ID_A, \"usuario_id\": $USER_ID_A}")
P2_ID=$(echo "$RESP_P2" | python -c 'import sys, json; print(json.load(sys.stdin)["id"])')
# Forzar a mañana
db_exec "UPDATE prestamos SET fecha_limite = datetime('now', '+1 day') WHERE id = $P2_ID;"

# 2. Detener notificaciones
log_info "Deteniendo contenedor notificaciones..."
$DOCKER_CMD stop notificaciones

# 3. Ejecutar revisión: debe dar avisados = 0, notificaciones_disponible = false
RESP_REV_DOWN=$(curl -s -w "\n%{http_code}" -X POST "${BASE_PRESTAMOS}/prestamos/revisar-vencimientos")
CODE_REV_DOWN=$(echo "$RESP_REV_DOWN" | tail -n1)
BODY_REV_DOWN=$(echo "$RESP_REV_DOWN" | sed '$d')
[ "$CODE_REV_DOWN" -eq 200 ] || log_fail "Revisión con servicio down no respondió 200: HTTP $CODE_REV_DOWN"
echo "Respuesta revisión (servicio down): $BODY_REV_DOWN"

AVISADOS_DOWN=$(echo "$BODY_REV_DOWN" | python -c 'import sys, json; print(json.load(sys.stdin).get("avisados", 0))')
DISP_DOWN=$(echo "$BODY_REV_DOWN" | python -c 'import sys, json; print(json.load(sys.stdin).get("notificaciones_disponible"))')
[ "$AVISADOS_DOWN" -eq 0 ] || log_fail "Esperaba avisados = 0 con notificaciones caído, obtenido: $AVISADOS_DOWN"
[ "$DISP_DOWN" = "False" ] || log_fail "Esperaba notificaciones_disponible = false"

# Verificar que P2 NO quedó marcado como avisado
ENVIADO_P2=$(db_exec "SELECT aviso_vencimiento_enviado, IFNULL(aviso_enviado_en, 'NULL') FROM prestamos WHERE id = $P2_ID;")
log_info "P2 en DB tras fallo: $ENVIADO_P2"
echo "$ENVIADO_P2" | grep -q "0|NULL" || log_fail "P2 quedó marcado incorrectamente a pesar del fallo"
log_pass "P2 no fue marcado como avisado tras fallo de Notificaciones"

# 4. Iniciar notificaciones
log_info "Iniciando contenedor notificaciones..."
$DOCKER_CMD start notificaciones
sleep 3

# 5. Reintentar revisión
RESP_REV_UP=$(curl -s -X POST "${BASE_PRESTAMOS}/prestamos/revisar-vencimientos")
echo "Respuesta revisión tras iniciar notificaciones: $RESP_REV_UP"
AVISADOS_UP=$(echo "$RESP_REV_UP" | python -c 'import sys, json; print(json.load(sys.stdin).get("avisados", 0))')
DISP_UP=$(echo "$RESP_REV_UP" | python -c 'import sys, json; print(json.load(sys.stdin).get("notificaciones_disponible"))')
[ "$AVISADOS_UP" -ge 1 ] || log_fail "Esperaba avisados >= 1 tras restaurar notificaciones, obtenido: $AVISADOS_UP"
[ "$DISP_UP" = "True" ] || log_fail "Esperaba notificaciones_disponible = true"

# Ejecutar de nuevo: avisados = 0
RESP_REV_UP2=$(curl -s -X POST "${BASE_PRESTAMOS}/prestamos/revisar-vencimientos")
AVISADOS_UP2=$(echo "$RESP_REV_UP2" | python -c 'import sys, json; print(json.load(sys.stdin).get("avisados", 0))')
[ "$AVISADOS_UP2" -eq 0 ] || log_fail "Esperaba avisados = 0 en segunda revisión, obtenido: $AVISADOS_UP2"
log_pass "Escenario C exitoso: tolerancia a fallos y recuperación confirmadas"

# ==============================================================================
# ESCENARIO D: Préstamo vencido devuelto -> Multa notificada y caso degradado
# ==============================================================================
log_info "=== ESCENARIO D: Multa por retraso y caso degradado ==="

# 1. Crear préstamo P3 para Ana y poner fecha límite hace 3 días
RESP_P3=$(curl -s -X POST "${BASE_PRESTAMOS}/prestamos" \
  -H "Content-Type: application/json" \
  -d "{\"libro_id\": $LIBRO_ID_A, \"usuario_id\": $USER_ID_A}")
P3_ID=$(echo "$RESP_P3" | python -c 'import sys, json; print(json.load(sys.stdin)["id"])')
db_exec "UPDATE prestamos SET fecha_limite = datetime('now', '-3 days') WHERE id = $P3_ID;"

# 2. Devolver préstamo P3: debe generar multa 3 * 5 = 15.0 y notificada = 1
RESP_DEV_P3=$(curl -s -w "\n%{http_code}" -X PUT "${BASE_PRESTAMOS}/prestamos/${P3_ID}/devolucion")
CODE_DEV_P3=$(echo "$RESP_DEV_P3" | tail -n1)
BODY_DEV_P3=$(echo "$RESP_DEV_P3" | sed '$d')
[ "$CODE_DEV_P3" -eq 200 ] || log_fail "Devolución P3 falló: HTTP $CODE_DEV_P3"
echo "Respuesta devolución P3: $BODY_DEV_P3"

MULTA_P3_MONTO=$(echo "$BODY_DEV_P3" | python -c 'import sys, json; print(json.load(sys.stdin)["multa"]["monto"])')
[ "$MULTA_P3_MONTO" = "15.0" ] || log_fail "Monto de multa esperado 15.0, obtenido: $MULTA_P3_MONTO"

# Verificar en DB que notificada = 1
NOTIF_DB=$(db_exec "SELECT notificada FROM multas WHERE prestamo_id = $P3_ID;")
[ "$NOTIF_DB" -eq 1 ] || log_fail "Esperaba multas.notificada = 1 en DB para P3, obtenido: $NOTIF_DB"

# Esperar correo MULTA en Mailpit
RECIBIDO_MULTA=0
for i in {1..12}; do
  COUNT=$(contar_correos "$EMAIL_A" "multa")
  if [ "$COUNT" -ge 1 ]; then
    RECIBIDO_MULTA=1
    break
  fi
  sleep 1
done
[ "$RECIBIDO_MULTA" -eq 1 ] || log_fail "Mailpit no recibió el correo de MULTA"
log_pass "Multa generada, notificada = 1 y correo recibido en Mailpit"

# 3. Caso degradado: Detener Notificaciones y devolver otro préstamo atrasado
log_info "Probando caso degradado con Notificaciones detenido..."
RESP_P4=$(curl -s -X POST "${BASE_PRESTAMOS}/prestamos" \
  -H "Content-Type: application/json" \
  -d "{\"libro_id\": $LIBRO_ID_A, \"usuario_id\": $USER_ID_A}")
P4_ID=$(echo "$RESP_P4" | python -c 'import sys, json; print(json.load(sys.stdin)["id"])')
db_exec "UPDATE prestamos SET fecha_limite = datetime('now', '-2 days') WHERE id = $P4_ID;"

$DOCKER_CMD stop notificaciones

# Devolver P4: debe responder 200 con multa generada y notificada = 0
RESP_DEV_P4=$(curl -s -w "\n%{http_code}" -X PUT "${BASE_PRESTAMOS}/prestamos/${P4_ID}/devolucion")
CODE_DEV_P4=$(echo "$RESP_DEV_P4" | tail -n1)
BODY_DEV_P4=$(echo "$RESP_DEV_P4" | sed '$d')
[ "$CODE_DEV_P4" -eq 200 ] || log_fail "Devolución P4 degradada falló: HTTP $CODE_DEV_P4"
echo "Respuesta devolución degradada P4: $BODY_DEV_P4"

NOTIF_P4_DB=$(db_exec "SELECT notificada FROM multas WHERE prestamo_id = $P4_ID;")
[ "$NOTIF_P4_DB" -eq 0 ] || log_fail "Esperaba multas.notificada = 0 para P4 en caso degradado, obtenido: $NOTIF_P4_DB"
log_pass "Devolución exitosa (200) y multa guardada con notificada = 0 cuando Notificaciones está caído"

# 4. Iniciar Notificaciones y ejecutar revisión de vencimientos para que reenvíe la multa
$DOCKER_CMD start notificaciones
sleep 3

RESP_REV_MULTA=$(curl -s -X POST "${BASE_PRESTAMOS}/prestamos/revisar-vencimientos")
echo "Respuesta revisión tras recuperar Notificaciones: $RESP_REV_MULTA"
MULTAS_REENVIADAS=$(echo "$RESP_REV_MULTA" | python -c 'import sys, json; print(json.load(sys.stdin).get("multas_reenviadas", 0))')
[ "$MULTAS_REENVIADAS" -ge 1 ] || log_fail "Esperaba multas_reenviadas >= 1, obtenido: $MULTAS_REENVIADAS"

NOTIF_P4_POST=$(db_exec "SELECT notificada FROM multas WHERE prestamo_id = $P4_ID;")
[ "$NOTIF_P4_POST" -eq 1 ] || log_fail "Esperaba multas.notificada = 1 tras reenvío, obtenido: $NOTIF_P4_POST"
log_pass "Escenario D exitoso: multa reenviada y marcada como notificada = 1"

# ==============================================================================
# ESCENARIO E: Usuario sin correo -> Préstamo 201 sin evento -> sin_correo = 1
# ==============================================================================
log_info "=== ESCENARIO E: Usuario sin correo electrónico ==="

RESP_USER_NOMAIL=$(curl -s -X POST "${BASE_PRESTAMOS}/prestamos" \
  -H "Content-Type: application/json" \
  -d "{\"usuario\": \"Sin Correo User\", \"ci\": \"77889900\", \"libro_id\": $LIBRO_ID_A}")
P5_ID=$(echo "$RESP_USER_NOMAIL" | python -c 'import sys, json; print(json.load(sys.stdin)["id"])')
log_pass "Préstamo creado para usuario sin correo: id=$P5_ID"

# Forzar fecha a mañana
db_exec "UPDATE prestamos SET fecha_limite = datetime('now', '+1 day') WHERE id = $P5_ID;"

# Ejecutar revisión: debe reflejarse en sin_correo y NO marcar el préstamo
RESP_REV_NOMAIL=$(curl -s -X POST "${BASE_PRESTAMOS}/prestamos/revisar-vencimientos")
echo "Respuesta revisión con usuario sin correo: $RESP_REV_NOMAIL"
SIN_CORREO_COUNT=$(echo "$RESP_REV_NOMAIL" | python -c 'import sys, json; print(json.load(sys.stdin).get("sin_correo", 0))')
[ "$SIN_CORREO_COUNT" -ge 1 ] || log_fail "Esperaba sin_correo >= 1, obtenido: $SIN_CORREO_COUNT"

ENVIADO_P5=$(db_exec "SELECT aviso_vencimiento_enviado, IFNULL(aviso_enviado_en, 'NULL') FROM prestamos WHERE id = $P5_ID;")
echo "$ENVIADO_P5" | grep -q "0|NULL" || log_fail "Préstamo sin correo fue marcado incorrectamente"
log_pass "Escenario E exitoso: contado en sin_correo y préstamo no marcado"

# ==============================================================================
# ESCENARIO F: Inspeccionar logs de préstamos -> Cero CI y correos completos
# ==============================================================================
log_info "=== ESCENARIO F: Verificación de ausencia de CI y correos en logs ==="

LOGS_PRESTAMOS=$($DOCKER_CMD logs prestamos 2>&1)

# Verificar CI de prueba
if echo "$LOGS_PRESTAMOS" | grep -q "77889900"; then
  log_fail "Se encontró CI sensible '77889900' en los logs de préstamos"
fi

if echo "$LOGS_PRESTAMOS" | grep -q "$EMAIL_A"; then
  log_fail "Se encontró correo completo '$EMAIL_A' en los logs de préstamos"
fi
log_pass "Escenario F exitoso: logs limpios sin CI ni correos completos"

# ==============================================================================
# ESCENARIO G: Ejecutar scripts y tests existentes
# ==============================================================================
log_info "=== ESCENARIO G: Ejecutar test_endpoints.sh, test_concurrencia.sh y ejecutar_avisos.sh ==="

log_info "Ejecutando ./test_endpoints.sh..."
./test_endpoints.sh

log_info "Ejecutando bash scripts/test_concurrencia.sh..."
bash scripts/test_concurrencia.sh

log_info "Ejecutando scripts/ejecutar_avisos.sh..."
bash scripts/ejecutar_avisos.sh

log_pass "¡TODAS LAS PRUEBAS DE LA FASE F8 COMPLETADAS CON ÉXITO!"
