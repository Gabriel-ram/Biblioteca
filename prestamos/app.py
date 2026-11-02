import os
import logging
from datetime import datetime, timedelta
import requests
from flask import Flask, request, jsonify, render_template
from database import init_db, get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("prestamos")

app = Flask(__name__)

# Configuration from Environment Variables
CATALOGO_URL = os.getenv("CATALOGO_URL", "http://catalogo:8001")
NOTIFICACIONES_URL = os.getenv("NOTIFICACIONES_URL", "http://notificaciones:8003")
DIAS_PRESTAMO = int(os.getenv("DIAS_PRESTAMO", 7))
MULTA_POR_DIA = float(os.getenv("MULTA_POR_DIA", 5))
DIAS_AVISO = int(os.getenv("DIAS_AVISO", 2))
REQUEST_TIMEOUT = 3

with app.app_context():
    init_db()

def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        return datetime.strptime(date_str, "%Y-%m-%d")

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "UP"}), 200

@app.route('/', methods=['GET'])
def demo():
    return render_template('index.html')

@app.route('/demo/datos', methods=['GET'])
def datos_demo():
    """Aggregate data for the browser while tolerating a stopped notification service."""
    try:
        catalogo_response = requests.get(
            f"{CATALOGO_URL.rstrip('/')}/libros", timeout=REQUEST_TIMEOUT
        )
        catalogo_response.raise_for_status()
        libros = catalogo_response.json()
        autores_response = requests.get(
            f"{CATALOGO_URL.rstrip('/')}/autores", timeout=REQUEST_TIMEOUT
        )
        autores_response.raise_for_status()
        autores = autores_response.json()
    except (requests.RequestException, ValueError) as err:
        logger.error(f"No se pudieron cargar los libros del Catálogo: {err}")
        return jsonify({"error": "El servicio de Catálogo no está disponible"}), 503

    conn = get_db_connection()
    try:
        prestamos = [dict(row) for row in conn.execute(
            "SELECT * FROM prestamos ORDER BY id DESC"
        ).fetchall()]
        usuarios = [dict(row) for row in conn.execute(
            "SELECT * FROM usuarios ORDER BY nombre ASC"
        ).fetchall()]
    finally:
        conn.close()

    notificaciones = []
    notificaciones_disponibles = True
    try:
        response = requests.get(
            f"{NOTIFICACIONES_URL.rstrip('/')}/notificaciones",
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        notificaciones = response.json()
    except (requests.RequestException, ValueError) as err:
        notificaciones_disponibles = False
        logger.warning(f"Historial de notificaciones no disponible: {err}")

    return jsonify({
        "libros": libros,
        "autores": autores,
        "prestamos": prestamos,
        "usuarios": usuarios,
        "notificaciones": notificaciones,
        "notificaciones_disponibles": notificaciones_disponibles
    }), 200

# --- PRESTAMOS ENDPOINTS ---

@app.route('/prestamos', methods=['POST'])
def crear_prestamo():
    data = request.get_json() or {}
    usuario = data.get('usuario')
    ci = str(data.get('ci', '')).strip()
    libro_id = data.get('libro_id')

    if not usuario or not ci or not libro_id:
        return jsonify({"error": "Los campos 'usuario', 'ci' y 'libro_id' son obligatorios"}), 400
    if not ci.isascii() or not ci.isdigit() or len(ci) > 8:
        return jsonify({"error": "El CI debe contener solo números y tener como máximo 8 dígitos"}), 400

    # 1. Realizar llamada HTTP a Catálogo para descontar disponibilidad
    catalogo_patch_url = f"{CATALOGO_URL.rstrip('/')}/libros/{libro_id}/disponibilidad"
    try:
        response = requests.patch(catalogo_patch_url, json={"operacion": "descontar"}, timeout=REQUEST_TIMEOUT)
        if response.status_code == 409:
            return jsonify({"error": "El libro no se encuentra disponible"}), 409
        elif response.status_code != 200:
            try:
                detalle = (
                    response.json()
                    if 'application/json' in response.headers.get('content-type', '')
                    else response.text
                )
            except ValueError:
                detalle = response.text
            return jsonify({
                "error": "Error al comunicar con el catálogo de libros",
                "detalle": detalle
            }), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error conectando con Catálogo: {e}")
        return jsonify({"error": "No se pudo establecer comunicación con el servicio de Catálogo"}), 503

    # 2. Calcular fechas y registrar préstamo localmente
    fecha_actual_dt = datetime.now()
    fecha_limite_dt = fecha_actual_dt + timedelta(days=DIAS_PRESTAMO)
    
    fecha_prestamo_str = fecha_actual_dt.isoformat()
    fecha_limite_str = fecha_limite_dt.isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO prestamos (usuario, ci, libro_id, fecha_prestamo, fecha_limite, estado)
            VALUES (?, ?, ?, ?, ?, 'ACTIVO')
            """,
            (usuario, ci, libro_id, fecha_prestamo_str, fecha_limite_str)
        )
        cursor.execute(
            "INSERT OR IGNORE INTO usuarios (nombre, ci, fecha_registro) VALUES (?, ?, ?)",
            (usuario, ci, fecha_prestamo_str)
        )
        conn.commit()
        prestamo_id = cursor.lastrowid

        cursor.execute("SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))
        prestamo = dict(cursor.fetchone())
        conn.close()

        return jsonify(prestamo), 201

    except Exception as e:
        logger.error(f"Error al guardar préstamo localmente. Iniciando rollback en Catálogo: {e}")
        conn.rollback()
        conn.close()
        
        # Rollback en Catálogo reponiendo el stock
        try:
            rollback_response = requests.patch(
                catalogo_patch_url,
                json={"operacion": "reponer"},
                timeout=REQUEST_TIMEOUT
            )
            if rollback_response.status_code == 409:
                logger.warning(
                    f"Catálogo reportó 409 al reponer libro {libro_id} en rollback compensatorio: stock ya completo"
                )
            elif rollback_response.status_code != 200:
                logger.error(
                    "Catálogo rechazó la compensación de stock: "
                    f"HTTP {rollback_response.status_code}"
                )
        except requests.RequestException as rollback_err:
            logger.error(f"Error durante el rollback de stock en Catálogo: {rollback_err}")

        return jsonify({
            "error": "Error interno al procesar el préstamo; se intentó revertir la reserva del libro"
        }), 500

@app.route('/prestamos', methods=['GET'])
def listar_prestamos():
    usuario_filter = request.args.get('usuario')
    conn = get_db_connection()
    cursor = conn.cursor()

    if usuario_filter:
        cursor.execute("SELECT * FROM prestamos WHERE usuario = ?", (usuario_filter,))
    else:
        cursor.execute("SELECT * FROM prestamos")

    prestamos = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(prestamos), 200

@app.route('/prestamos/<int:prestamo_id>/devolucion', methods=['PUT'])
def registrar_devolucion(prestamo_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute("SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))
    row = cursor.fetchone()
    if not row:
        conn.rollback()
        conn.close()
        return jsonify({"error": "Préstamo no encontrado"}), 404

    prestamo = dict(row)
    if prestamo['estado'] != 'ACTIVO':
        conn.rollback()
        conn.close()
        return jsonify({"error": f"El préstamo ya se encuentra en estado '{prestamo['estado']}'"}), 400

    # Keep local writes serialized so concurrent return requests cannot restore stock twice.
    libro_id = prestamo['libro_id']
    catalogo_patch_url = f"{CATALOGO_URL.rstrip('/')}/libros/{libro_id}/disponibilidad"
    try:
        response = requests.patch(
            catalogo_patch_url,
            json={"operacion": "reponer"},
            timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as err:
        conn.rollback()
        conn.close()
        logger.error(f"No se pudo reponer el libro {libro_id} en Catálogo: {err}")
        return jsonify({
            "error": "Catálogo no está disponible; el préstamo continúa activo"
        }), 503

    if response.status_code == 409:
        logger.warning(
            f"Catálogo reportó 409 al reponer libro {libro_id} (ejemplares ya al máximo); continuando con la devolución"
        )
    elif response.status_code != 200:
        conn.rollback()
        conn.close()
        logger.error(
            f"Catálogo rechazó la reposición del libro {libro_id}: "
            f"HTTP {response.status_code}"
        )
        return jsonify({
            "error": "Catálogo no confirmó la reposición; el préstamo continúa activo",
            "detalle": response.text
        }), 502

    try:
        fecha_devolucion_dt = datetime.now()
        fecha_devolucion_str = fecha_devolucion_dt.isoformat()
        fecha_limite_dt = parse_date(prestamo['fecha_limite'])

        cursor.execute(
            "UPDATE prestamos SET fecha_devolucion = ?, estado = 'DEVUELTO' WHERE id = ?",
            (fecha_devolucion_str, prestamo_id)
        )

        multa_info = None
        dias_retraso = (fecha_devolucion_dt.date() - fecha_limite_dt.date()).days
        if dias_retraso > 0:
            monto_multa = dias_retraso * MULTA_POR_DIA
            cursor.execute(
                """
                INSERT INTO multas (prestamo_id, dias_retraso, monto, estado)
                VALUES (?, ?, ?, 'PENDIENTE')
                """,
                (prestamo_id, dias_retraso, monto_multa)
            )
            multa_info = {
                "id": cursor.lastrowid,
                "prestamo_id": prestamo_id,
                "dias_retraso": dias_retraso,
                "monto": monto_multa,
                "estado": "PENDIENTE"
            }
        conn.commit()
    except Exception as err:
        conn.rollback()
        conn.close()
        logger.exception(
            f"Error guardando devolución #{prestamo_id}; intentando revertir stock"
        )
        try:
            compensation = requests.patch(
                catalogo_patch_url,
                json={"operacion": "descontar"},
                timeout=REQUEST_TIMEOUT
            )
            if compensation.status_code != 200:
                logger.error(
                    "Catálogo no aceptó la compensación tras fallo local: "
                    f"HTTP {compensation.status_code}"
                )
        except requests.RequestException as compensation_err:
            logger.error(f"Falló la compensación de inventario: {compensation_err}")
        return jsonify({
            "error": "No se pudo guardar la devolución localmente; se intentó revertir el stock"
        }), 500

    cursor.execute("SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))
    prestamo_actualizado = dict(cursor.fetchone())
    conn.close()

    # Notification delivery is best-effort: it must not undo a successful return.
    if multa_info:
        notif_url = f"{NOTIFICACIONES_URL.rstrip('/')}/notificar"
        mensaje_notif = (
            f"Estimado/a {prestamo['usuario']}, su devolución del préstamo #{prestamo_id} registró "
            f"{dias_retraso} días de retraso. Se ha generado una multa de ${monto_multa:.2f}."
        )
        try:
            notif_response = requests.post(
                notif_url,
                json={"tipo": "MULTA", "usuario": prestamo['usuario'], "mensaje": mensaje_notif},
                timeout=REQUEST_TIMEOUT
            )
            if notif_response.status_code not in (200, 202):
                logger.warning(
                    f"Notificaciones rechazó la multa: HTTP {notif_response.status_code}"
                )
        except requests.RequestException as err:
            logger.error(f"Fallo al enviar notificación de multa: {err}")

    respuesta = {
        "mensaje": "Devolución registrada exitosamente",
        "prestamo": prestamo_actualizado
    }
    if multa_info:
        respuesta["multa"] = multa_info

    return jsonify(respuesta), 200

@app.route('/prestamos/revisar-vencimientos', methods=['POST'])
def revisar_vencimientos():
    conn = get_db_connection()
    cursor = conn.cursor()
    ahora = datetime.now().date()
    notificaciones_enviadas = 0
    notif_url = f"{NOTIFICACIONES_URL.rstrip('/')}/notificar"

    # Serialize batch runs and only mark an alert after Notificaciones accepts it.
    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute(
        "SELECT * FROM prestamos WHERE estado = 'ACTIVO' "
        "AND aviso_vencimiento_enviado = 0"
    )
    prestamos_activos = [dict(row) for row in cursor.fetchall()]

    for prestamo in prestamos_activos:
        fecha_limite_dt = parse_date(prestamo['fecha_limite'])
        if not fecha_limite_dt:
            continue

        dias_restantes = (fecha_limite_dt.date() - ahora).days
        if dias_restantes <= DIAS_AVISO:
            payload = {
                "tipo": "POR_VENCER",
                "usuario": prestamo['usuario'],
                "mensaje": (
                    f"RECORDATORIO: El préstamo #{prestamo['id']} (Libro ID #{prestamo['libro_id']}) "
                    f"vence el {fecha_limite_dt.strftime('%Y-%m-%d')}. Días restantes: {dias_restantes}."
                )
            }
            try:
                resp = requests.post(notif_url, json=payload, timeout=REQUEST_TIMEOUT)
                if resp.status_code in (200, 202):
                    cursor.execute(
                        "UPDATE prestamos SET aviso_vencimiento_enviado = 1 WHERE id = ?",
                        (prestamo['id'],)
                    )
                    notificaciones_enviadas += 1
                else:
                    logger.warning(
                        f"Notificaciones rechazó aviso para préstamo #{prestamo['id']}: "
                        f"HTTP {resp.status_code}"
                    )
            except requests.RequestException as err:
                logger.error(
                    f"Error enviando aviso por vencer para préstamo #{prestamo['id']}: {err}"
                )

    conn.commit()
    conn.close()

    return jsonify({
        "status": "Revisión de vencimientos completada",
        "prestamos_revisados": len(prestamos_activos),
        "notificaciones_enviadas": notificaciones_enviadas
    }), 200

# --- PROXY CATÁLOGO (LIBROS Y AUTORES) ---

@app.route('/libros', methods=['POST'])
def proxy_crear_libro():
    try:
        resp = requests.post(
            f"{CATALOGO_URL.rstrip('/')}/libros",
            json=request.get_json(),
            timeout=REQUEST_TIMEOUT
        )
        data = resp.json() if 'application/json' in resp.headers.get('content-type', '') else {"mensaje": resp.text}
        return jsonify(data), resp.status_code
    except requests.RequestException as e:
        logger.error(f"Error comunicando con Catálogo al crear libro: {e}")
        return jsonify({"error": "No se pudo comunicar con el servicio de Catálogo"}), 503

@app.route('/libros/<int:libro_id>', methods=['PUT'])
def proxy_actualizar_libro(libro_id):
    try:
        resp = requests.put(
            f"{CATALOGO_URL.rstrip('/')}/libros/{libro_id}",
            json=request.get_json(),
            timeout=REQUEST_TIMEOUT
        )
        data = resp.json() if 'application/json' in resp.headers.get('content-type', '') else {"mensaje": resp.text}
        return jsonify(data), resp.status_code
    except requests.RequestException as e:
        logger.error(f"Error comunicando con Catálogo al actualizar libro {libro_id}: {e}")
        return jsonify({"error": "No se pudo comunicar con el servicio de Catálogo"}), 503

@app.route('/libros/<int:libro_id>', methods=['DELETE'])
def proxy_eliminar_libro(libro_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM prestamos WHERE libro_id = ? AND estado = 'ACTIVO'", (libro_id,))
    activos = cursor.fetchone()['count']
    conn.close()
    if activos > 0:
        return jsonify({
            "error": f"No se puede eliminar el libro: tiene {activos} préstamo(s) activo(s) en curso."
        }), 400

    try:
        resp = requests.delete(
            f"{CATALOGO_URL.rstrip('/')}/libros/{libro_id}",
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 204:
            return '', 204
        data = resp.json() if 'application/json' in resp.headers.get('content-type', '') else {"error": resp.text}
        return jsonify(data), resp.status_code
    except requests.RequestException as e:
        logger.error(f"Error comunicando con Catálogo al eliminar libro {libro_id}: {e}")
        return jsonify({"error": "No se pudo comunicar con el servicio de Catálogo"}), 503

@app.route('/autores', methods=['POST'])
def proxy_crear_autor():
    try:
        resp = requests.post(
            f"{CATALOGO_URL.rstrip('/')}/autores",
            json=request.get_json(),
            timeout=REQUEST_TIMEOUT
        )
        data = resp.json() if 'application/json' in resp.headers.get('content-type', '') else {"mensaje": resp.text}
        return jsonify(data), resp.status_code
    except requests.RequestException as e:
        logger.error(f"Error comunicando con Catálogo al crear autor: {e}")
        return jsonify({"error": "No se pudo comunicar con el servicio de Catálogo"}), 503

@app.route('/prestamos/<int:prestamo_id>', methods=['DELETE'])
def eliminar_prestamo(prestamo_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Préstamo no encontrado"}), 404
    prestamo = dict(row)
    # Solo se permite eliminar préstamos ya devueltos.
    # Si está ACTIVO, el libro sigue fuera de stock; el flujo correcto es
    # registrar la devolución primero (PUT /prestamos/<id>/devolucion).
    if prestamo['estado'] == 'ACTIVO':
        conn.close()
        return jsonify({
            "error": "No se puede eliminar un préstamo activo. "
                     "Registre la devolución primero (PUT /prestamos/<id>/devolucion)."
        }), 409
    cursor.execute("DELETE FROM prestamos WHERE id = ?", (prestamo_id,))
    cursor.execute("DELETE FROM multas WHERE prestamo_id = ?", (prestamo_id,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": f"Préstamo #{prestamo_id} eliminado exitosamente"}), 200


# --- USUARIOS ENDPOINTS ---

@app.route('/usuarios', methods=['GET'])
def listar_usuarios():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios ORDER BY nombre ASC")
    usuarios = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(usuarios), 200

@app.route('/usuarios', methods=['POST'])
def crear_usuario():
    data = request.get_json() or {}
    nombre = str(data.get('nombre', '')).strip()
    ci = str(data.get('ci', '')).strip()

    if not nombre or not ci:
        return jsonify({"error": "Los campos 'nombre' y 'ci' son obligatorios"}), 400
    if not ci.isascii() or not ci.isdigit() or len(ci) > 8:
        return jsonify({"error": "El CI debe contener solo números y tener como máximo 8 dígitos"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE ci = ?", (ci,))
    existente = cursor.fetchone()
    if existente:
        conn.close()
        return jsonify({"error": f"Ya existe un usuario registrado con el CI {ci}"}), 409

    fecha_registro = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO usuarios (nombre, ci, fecha_registro) VALUES (?, ?, ?)",
        (nombre, ci, fecha_registro)
    )
    conn.commit()
    user_id = cursor.lastrowid
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usuario = dict(cursor.fetchone())
    conn.close()
    return jsonify(usuario), 201

@app.route('/usuarios/<int:usuario_id>', methods=['DELETE'])
def eliminar_usuario(usuario_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Usuario no encontrado"}), 404
    user = dict(row)
    cursor.execute("SELECT COUNT(*) as count FROM prestamos WHERE ci = ? AND estado = 'ACTIVO'", (user['ci'],))
    activos = cursor.fetchone()['count']
    if activos > 0:
        conn.close()
        return jsonify({"error": f"No se puede eliminar: el usuario tiene {activos} préstamo(s) activo(s) en curso."}), 400

    cursor.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": f"Usuario {user['nombre']} eliminado exitosamente"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8002, debug=True)

