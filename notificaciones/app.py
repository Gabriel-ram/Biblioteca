import os
import re
import sys
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from database import init_db, get_db_connection
from mailer import enmascarar_correo
from worker import start_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notificaciones")

app = Flask(__name__)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TIPOS_VALIDOS = {'PRESTAMO', 'POR_VENCER', 'MULTA'}


def validar_formato_correo(correo: str) -> bool:
    if not correo or not isinstance(correo, str):
        return False
    return bool(EMAIL_REGEX.match(correo.strip()))


with app.app_context():
    init_db()
    start_worker()


@app.route('/health', methods=['GET'])
def health_check():
    """Devuelve estado de salud y conteo de notificaciones PENDIENTES."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as pendientes FROM notificaciones WHERE estado = 'PENDIENTE'")
        row = cursor.fetchone()
        pendientes = row['pendientes'] if row else 0
        conn.close()
        return jsonify({"status": "UP", "pendientes": pendientes}), 200
    except Exception as e:
        logger.error(f"Error en health check: {e}")
        return jsonify({"status": "DOWN", "error": str(e)}), 500


@app.route('/notificar', methods=['POST'])
def crear_notificacion():
    data = request.get_json() or {}
    tipo_raw = data.get('tipo')
    usuario_raw = data.get('usuario')
    correo_raw = data.get('correo') or data.get('correo_destino') or data.get('email')
    mensaje = str(data.get('mensaje') or '').strip()
    datos_raw = data.get('datos') or {}
    clave_raw = data.get('clave') or data.get('clave_idempotencia')
    asunto_raw = data.get('asunto')

    # 1. Validación de campos obligatorios
    if not tipo_raw or not isinstance(tipo_raw, str):
        return jsonify({"error": "El campo 'tipo' es obligatorio"}), 400

    tipo = tipo_raw.strip().upper()
    if tipo not in TIPOS_VALIDOS:
        return jsonify({"error": f"El campo 'tipo' debe ser uno de: {sorted(list(TIPOS_VALIDOS))}"}), 400

    if not usuario_raw or not str(usuario_raw).strip():
        return jsonify({"error": "El campo 'usuario' es obligatorio"}), 400
    usuario = str(usuario_raw).strip()

    # 2. Validación de correo (o compatibilidad si no se proporciona)
    fecha_creacion = datetime.now().isoformat()
    if correo_raw is not None and str(correo_raw).strip():
        correo_str = str(correo_raw).strip()
        if not validar_formato_correo(correo_str):
            return jsonify({"error": "El formato del correo electrónico es inválido"}), 400
        correo_destino = correo_str
        estado = 'PENDIENTE'
        proximo_intento = fecha_creacion
        ultimo_error = None
        intentos = 0
    else:
        # Compatibilidad: si falta correo, responde 202 igualmente y guarda como FALLIDA
        correo_destino = ''
        estado = 'FALLIDA'
        proximo_intento = None
        ultimo_error = 'sin correo destino'
        intentos = 0

    # 3. Serialización de datos y preparación de clave
    if isinstance(datos_raw, (dict, list)):
        datos_str = json.dumps(datos_raw)
    else:
        datos_str = str(datos_raw) if datos_raw else '{}'

    clave = str(clave_raw).strip() if clave_raw is not None and str(clave_raw).strip() else None
    asunto = str(asunto_raw).strip() if asunto_raw else None

    # Alerta en stdout (con correo enmascarado por seguridad)
    correo_log = enmascarar_correo(correo_destino) if correo_destino else '<sin correo destino>'
    print(f"\n================ [ALERTA DE NOTIFICACIÓN] ================", flush=True)
    print(f"Tipo:           {tipo}", flush=True)
    print(f"Usuario:        {usuario}", flush=True)
    print(f"Correo:         {correo_log}", flush=True)
    print(f"Estado inicial: {estado}", flush=True)
    print(f"Fecha Creación: {fecha_creacion}", flush=True)
    print(f"==========================================================\n", flush=True)
    sys.stdout.flush()

    # 4. Inserción con deduplicación por clave de idempotencia
    conn = get_db_connection()
    cursor = conn.cursor()

    if clave:
        cursor.execute(
            """
            INSERT OR IGNORE INTO notificaciones (
                tipo, usuario, correo_destino, asunto, mensaje, fecha_creacion,
                estado, intentos, proximo_intento, ultimo_error, clave_idempotencia, datos
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tipo, usuario, correo_destino, asunto, mensaje, fecha_creacion,
             estado, intentos, proximo_intento, ultimo_error, clave, datos_str)
        )
        conn.commit()

        if cursor.rowcount == 0:
            # Fila ignorada por clave existente: es un duplicado
            cursor.execute("SELECT id FROM notificaciones WHERE clave_idempotencia = ?", (clave,))
            row = cursor.fetchone()
            existente_id = row['id'] if row else None
            conn.close()
            return jsonify({
                "status": "registrado",
                "id": existente_id,
                "duplicada": True
            }), 202
        else:
            nuevo_id = cursor.lastrowid
            conn.close()
            return jsonify({
                "status": "registrado",
                "id": nuevo_id,
                "duplicada": False
            }), 202

    else:
        cursor.execute(
            """
            INSERT INTO notificaciones (
                tipo, usuario, correo_destino, asunto, mensaje, fecha_creacion,
                estado, intentos, proximo_intento, ultimo_error, clave_idempotencia, datos
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (tipo, usuario, correo_destino, asunto, mensaje, fecha_creacion,
             estado, intentos, proximo_intento, ultimo_error, datos_str)
        )
        conn.commit()
        nuevo_id = cursor.lastrowid
        conn.close()
        return jsonify({
            "status": "registrado",
            "id": nuevo_id,
            "duplicada": False
        }), 202


@app.route('/notificaciones', methods=['GET'])
def listar_notificaciones():
    """Lista las notificaciones ordenadas de más reciente a más antigua con filtros opcionales."""
    usuario_filtro = request.args.get('usuario')
    estado_filtro = request.args.get('estado')
    tipo_filtro = request.args.get('tipo')

    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM notificaciones WHERE 1=1"
    params = []

    if usuario_filtro:
        query += " AND usuario = ?"
        params.append(usuario_filtro.strip())

    if estado_filtro:
        query += " AND estado = ?"
        params.append(estado_filtro.strip().upper())

    if tipo_filtro:
        query += " AND tipo = ?"
        params.append(tipo_filtro.strip().upper())

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    notificaciones = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(notificaciones), 200


@app.route('/notificaciones/<int:notif_id>/reintentar', methods=['POST'])
def reintentar_notificacion(notif_id):
    """Reencola una notificación en estado FALLIDA que tenga correo destino."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notificaciones WHERE id = ?", (notif_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "Notificación no encontrada"}), 404

    notif = dict(row)
    correo_destino = (notif.get('correo_destino') or '').strip()

    if notif.get('estado') != 'FALLIDA' or not correo_destino:
        conn.close()
        return jsonify({
            "error": "Solo se pueden reintentar notificaciones en estado FALLIDA y con correo destino válido",
            "estado_actual": notif.get('estado'),
            "tiene_correo": bool(correo_destino)
        }), 409

    ahora_str = datetime.now().isoformat()
    cursor.execute(
        """
        UPDATE notificaciones
        SET estado = 'PENDIENTE', intentos = 0, proximo_intento = ?, ultimo_error = NULL
        WHERE id = ?
        """,
        (ahora_str, notif_id)
    )
    conn.commit()
    conn.close()

    logger.info(f"Notificación #{notif_id} reencolada para reintento manual (destino: {enmascarar_correo(correo_destino)})")
    return jsonify({
        "mensaje": "Notificación reencolada para reintento",
        "id": notif_id,
        "estado": "PENDIENTE"
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8003, debug=True)
