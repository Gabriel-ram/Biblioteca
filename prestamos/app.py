import os
import logging
from datetime import datetime, timedelta
import requests
from flask import Flask, request, jsonify, render_template
from database import init_db, get_db_connection
from clients import CatalogoClient, NotificacionesClient, ServicioNoDisponible

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("prestamos")

app = Flask(__name__)
from usuarios import usuarios_bp
app.register_blueprint(usuarios_bp)

# Clients for external microservices
catalogo_client = CatalogoClient()
notificaciones_client = NotificacionesClient()

# Configuration from Environment Variables
DIAS_PRESTAMO = int(os.getenv("DIAS_PRESTAMO", 7))
MULTA_POR_DIA = float(os.getenv("MULTA_POR_DIA", 5))
DIAS_AVISO = int(os.getenv("DIAS_AVISO", 2))
NOTIFICAR_PRESTAMO = os.getenv("NOTIFICAR_PRESTAMO", "true").lower() in ("true", "1", "yes")

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
    """Aggregate data for the browser while tolerating stopped catalog or notification services."""
    libros = []
    autores = []
    catalogo_disponible = True
    try:
        catalogo_response = catalogo_client.obtener_libros()
        catalogo_response.raise_for_status()
        libros = catalogo_response.json()
        autores_response = catalogo_client.obtener_autores()
        autores_response.raise_for_status()
        autores = autores_response.json()
    except (ServicioNoDisponible, requests.RequestException, ValueError) as err:
        catalogo_disponible = False
        logger.warning(f"No se pudieron cargar los libros del Catálogo: {err}")

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
        response = notificaciones_client.obtener_notificaciones()
        response.raise_for_status()
        notificaciones = response.json()
    except (ServicioNoDisponible, requests.RequestException, ValueError) as err:
        notificaciones_disponibles = False
        logger.warning(f"Historial de notificaciones no disponible: {err}")

    return jsonify({
        "libros": libros,
        "autores": autores,
        "prestamos": prestamos,
        "usuarios": usuarios,
        "notificaciones": notificaciones,
        "catalogo_disponible": catalogo_disponible,
        "notificaciones_disponibles": notificaciones_disponibles
    }), 200

# --- PRESTAMOS ENDPOINTS ---

@app.route('/prestamos', methods=['POST'])
def crear_prestamo():
    data = request.get_json() or {}
    libro_id = data.get('libro_id')
    if not libro_id:
        return jsonify({"error": "El campo 'libro_id' es obligatorio"}), 400

    dias_param = data.get('dias_prestamo')
    if dias_param is None or dias_param == '':
        dias_param = data.get('dias')

    if dias_param is not None and dias_param != '':
        try:
            dias_prestamo = int(dias_param)
            if dias_prestamo <= 0:
                return jsonify({"error": "El tiempo de préstamo (en días) debe ser mayor a 0"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "El tiempo de préstamo (en días) debe ser un número entero válido"}), 400
    else:
        dias_prestamo = DIAS_PRESTAMO

    usuario_id_param = data.get('usuario_id')
    codigo_usuario_param = data.get('codigo_usuario')

    conn = get_db_connection()
    cursor = conn.cursor()

    if usuario_id_param is not None or codigo_usuario_param is not None:
        # Formato nuevo: {libro_id, usuario_id} o {libro_id, codigo_usuario}
        if usuario_id_param is not None:
            cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id_param,))
        else:
            cursor.execute("SELECT * FROM usuarios WHERE codigo = ?", (str(codigo_usuario_param).strip(),))
        user_row = cursor.fetchone()
        if not user_row:
            conn.close()
            return jsonify({"error": "Usuario no encontrado"}), 404

        user_obj = dict(user_row)
        if not user_obj.get('activo', 1):
            conn.close()
            return jsonify({"error": "El usuario se encuentra inactivo"}), 409

        usuario_id = user_obj['id']
        usuario_nombre = user_obj['nombre']
        usuario_ci = user_obj.get('ci') or user_obj.get('codigo')

    else:
        # Formato antiguo: {libro_id, usuario, ci}
        usuario_nombre = str(data.get('usuario', '')).strip()
        ci = str(data.get('ci', '')).strip()

        if not usuario_nombre or not ci:
            conn.close()
            return jsonify({"error": "Los campos 'usuario', 'ci' y 'libro_id' son obligatorios"}), 400
        if not ci.isascii() or not ci.isdigit() or len(ci) > 8:
            conn.close()
            return jsonify({"error": "El CI debe contener solo números y tener como máximo 8 dígitos"}), 400

        # Busca el usuario por codigo = ci; si no existe, créalo como antes (correo vacío)
        cursor.execute("SELECT * FROM usuarios WHERE codigo = ? OR ci = ?", (ci, ci))
        user_row = cursor.fetchone()
        if user_row:
            user_obj = dict(user_row)
            if not user_obj.get('activo', 1):
                conn.close()
                return jsonify({"error": "El usuario se encuentra inactivo"}), 409
            usuario_id = user_obj['id']
            usuario_nombre = user_obj['nombre']
            usuario_ci = user_obj.get('ci') or ci
        else:
            fecha_reg = datetime.now().isoformat()
            cursor.execute(
                """
                INSERT INTO usuarios (nombre, ci, codigo, correo, tipo, activo, fecha_registro)
                VALUES (?, ?, ?, '', 'ESTUDIANTE', 1, ?)
                """,
                (usuario_nombre, ci, ci, fecha_reg)
            )
            conn.commit()
            usuario_id = cursor.lastrowid
            usuario_ci = ci

    conn.close()

    # 1. Realizar llamada HTTP a Catálogo para descontar disponibilidad
    try:
        response = catalogo_client.descontar_disponibilidad(libro_id)
        if response.status_code == 409:
            return jsonify({"error": "El libro no se encuentra disponible"}), 409
        elif response.status_code == 404:
            return jsonify({"error": "Libro no encontrado"}), 404
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
    except ServicioNoDisponible as e:
        logger.error(f"Error conectando con Catálogo: {e}")
        return jsonify({"error": "No se pudo establecer comunicación con el servicio de Catálogo"}), 503

    libro_data = response.json() if response.status_code == 200 else {}
    libro_titulo = libro_data.get('titulo', '')

    # 2. Calcular fechas y registrar préstamo localmente
    fecha_actual_dt = datetime.now()
    fecha_limite_dt = fecha_actual_dt + timedelta(days=dias_prestamo)
    
    fecha_prestamo_str = fecha_actual_dt.isoformat()
    fecha_limite_str = fecha_limite_dt.isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO prestamos (
                usuario, ci, libro_id, fecha_prestamo, fecha_limite, estado,
                aviso_vencimiento_enviado, usuario_id, libro_titulo, dias_prestamo
            )
            VALUES (?, ?, ?, ?, ?, 'ACTIVO', 0, ?, ?, ?)
            """,
            (usuario_nombre, usuario_ci, libro_id, fecha_prestamo_str, fecha_limite_str, usuario_id, libro_titulo, dias_prestamo)
        )
        conn.commit()
        prestamo_id = cursor.lastrowid

        cursor.execute("SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))
        prestamo = dict(cursor.fetchone())

        correo_usuario = ""
        if usuario_id:
            cursor.execute("SELECT correo FROM usuarios WHERE id = ?", (usuario_id,))
            u_row = cursor.fetchone()
            if u_row and u_row['correo']:
                correo_usuario = str(u_row['correo']).strip()
        conn.close()

        if NOTIFICAR_PRESTAMO:
            if not correo_usuario:
                logger.info(f"Préstamo #{prestamo_id} registrado sin notificación: usuario sin correo")
            else:
                fecha_limite_dt = parse_date(prestamo['fecha_limite'])
                fecha_limite_legible = fecha_limite_dt.strftime('%Y-%m-%d') if fecha_limite_dt else str(prestamo['fecha_limite'])[:10]
                try:
                    notificaciones_client.enviar_notificacion(
                        tipo="PRESTAMO",
                        usuario=usuario_nombre,
                        correo=correo_usuario,
                        datos={
                            "titulo": libro_titulo,
                            "fecha_limite": fecha_limite_legible,
                            "dias_prestamo": dias_prestamo
                        },
                        clave=f"PRESTAMO:{prestamo_id}"
                    )
                except ServicioNoDisponible as err:
                    logger.warning(f"No se pudo enviar notificación para préstamo #{prestamo_id}: {err}")

        return jsonify(prestamo), 201

    except Exception as e:
        logger.error(f"Error al guardar préstamo localmente para libro_id={libro_id}. Iniciando rollback en Catálogo: {e}")
        conn.rollback()
        conn.close()
        
        # Rollback en Catálogo reponiendo el stock
        try:
            rollback_response = catalogo_client.reponer_disponibilidad(libro_id)
            if rollback_response.status_code == 409:
                logger.warning(
                    f"Catálogo reportó 409 al reponer libro {libro_id} en rollback compensatorio: stock ya completo"
                )
            elif rollback_response.status_code != 200:
                logger.critical(
                    f"CRITICAL: Catálogo rechazó la compensación de stock para libro_id={libro_id}, prestamo_id=None: "
                    f"HTTP {rollback_response.status_code}"
                )
        except ServicioNoDisponible as rollback_err:
            logger.critical(
                f"CRITICAL: Falló la compensación de stock en Catálogo para libro_id={libro_id}, prestamo_id=None: {rollback_err}"
            )

        return jsonify({
            "error": "Error interno al procesar el préstamo; se intentó revertir la reserva del libro"
        }), 500

@app.route('/prestamos', methods=['GET'])
def listar_prestamos():
    usuario_filter = request.args.get('usuario')
    usuario_id_filter = request.args.get('usuario_id')
    estado_filter = request.args.get('estado')

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM prestamos WHERE 1=1"
    params = []

    if usuario_filter:
        query += " AND usuario = ?"
        params.append(usuario_filter)
    if usuario_id_filter:
        query += " AND usuario_id = ?"
        params.append(usuario_id_filter)
    if estado_filter:
        query += " AND estado = ?"
        params.append(estado_filter)

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
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
    try:
        response = catalogo_client.reponer_disponibilidad(libro_id)
    except ServicioNoDisponible as err:
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
                INSERT INTO multas (prestamo_id, dias_retraso, monto, estado, notificada)
                VALUES (?, ?, ?, 'PENDIENTE', 0)
                """,
                (prestamo_id, dias_retraso, monto_multa)
            )
            multa_info = {
                "id": cursor.lastrowid,
                "prestamo_id": prestamo_id,
                "dias_retraso": dias_retraso,
                "monto": monto_multa,
                "estado": "PENDIENTE",
                "notificada": 0
            }
        conn.commit()
    except Exception as err:
        conn.rollback()
        conn.close()
        logger.exception(
            f"Error guardando devolución #{prestamo_id}; intentando revertir stock"
        )
        try:
            compensation = catalogo_client.descontar_disponibilidad(libro_id)
            if compensation.status_code != 200:
                logger.critical(
                    f"CRITICAL: Catálogo no aceptó la compensación tras fallo local en préstamo #{prestamo_id}, libro #{libro_id}: "
                    f"HTTP {compensation.status_code}"
                )
        except ServicioNoDisponible as compensation_err:
            logger.critical(f"CRITICAL: Falló la compensación de inventario para préstamo #{prestamo_id}, libro #{libro_id}: {compensation_err}")
        return jsonify({
            "error": "No se pudo guardar la devolución localmente; se intentó revertir el stock"
        }), 500

    cursor.execute("SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))
    prestamo_actualizado = dict(cursor.fetchone())

    # Obtener correo del usuario mientras la conexión está activa
    correo_usuario = ""
    usuario_nombre = prestamo['usuario']
    if prestamo.get('usuario_id'):
        cursor.execute("SELECT correo, nombre FROM usuarios WHERE id = ?", (prestamo['usuario_id'],))
        u_row = cursor.fetchone()
        if u_row:
            correo_usuario = (u_row['correo'] or '').strip()
            if u_row['nombre']:
                usuario_nombre = u_row['nombre']
    elif prestamo.get('ci'):
        cursor.execute("SELECT correo, nombre FROM usuarios WHERE codigo = ? OR ci = ?", (prestamo['ci'], prestamo['ci']))
        u_row = cursor.fetchone()
        if u_row:
            correo_usuario = (u_row['correo'] or '').strip()
            if u_row['nombre']:
                usuario_nombre = u_row['nombre']

    conn.close()

    # Envío de multa: best-effort, no anula la devolución si falla
    if multa_info:
        if not correo_usuario:
            logger.info(f"Multa para préstamo #{prestamo_id} registrada sin notificación: usuario sin correo")
        else:
            libro_titulo = prestamo.get('libro_titulo') or (prestamo_actualizado.get('libro_titulo') if prestamo_actualizado else '') or ''
            try:
                notif_response = notificaciones_client.enviar_notificacion(
                    tipo="MULTA",
                    usuario=usuario_nombre,
                    correo=correo_usuario,
                    datos={
                        "titulo": libro_titulo,
                        "monto": multa_info['monto'],
                        "dias_retraso": multa_info['dias_retraso']
                    },
                    clave=f"MULTA:{prestamo_id}"
                )
                if notif_response.status_code == 202:
                    conn_multa = get_db_connection()
                    try:
                        conn_multa.execute("UPDATE multas SET notificada = 1 WHERE id = ?", (multa_info['id'],))
                        conn_multa.commit()
                        multa_info['notificada'] = 1
                    finally:
                        conn_multa.close()
                else:
                    logger.warning(
                        f"Notificaciones rechazó la multa para préstamo #{prestamo_id}: HTTP {notif_response.status_code}"
                    )
            except ServicioNoDisponible as err:
                logger.warning(f"Fallo al enviar notificación de multa para préstamo #{prestamo_id}: {err}")

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

    revisados = 0
    avisados = 0
    multas_reenviadas = 0
    sin_correo = 0
    notificaciones_disponible = True

    try:
        # 1. Préstamos activos próximos a vencer
        cursor.execute("""
            SELECT p.id, p.libro_id, p.libro_titulo, p.fecha_limite, p.usuario, p.usuario_id, p.ci,
                   u.correo as usuario_correo, u.nombre as usuario_nombre_u
            FROM prestamos p
            LEFT JOIN usuarios u ON (p.usuario_id = u.id OR (p.usuario_id IS NULL AND (u.codigo = p.ci OR u.ci = p.ci)))
            WHERE p.estado = 'ACTIVO'
              AND p.aviso_enviado_en IS NULL
              AND p.aviso_vencimiento_enviado = 0
            ORDER BY p.id ASC
        """)
        candidatos = [dict(row) for row in cursor.fetchall()]

        for loan in candidatos:
            fecha_limite_dt = parse_date(loan['fecha_limite'])
            if not fecha_limite_dt:
                continue

            dias_restantes = (fecha_limite_dt.date() - ahora).days
            if 0 <= dias_restantes <= DIAS_AVISO:
                revisados += 1
                correo = (loan['usuario_correo'] or '').strip()
                if not correo:
                    sin_correo += 1
                    logger.info(f"Préstamo #{loan['id']} próximo a vencer sin aviso: usuario sin correo")
                    continue

                fecha_legible = fecha_limite_dt.strftime('%Y-%m-%d')
                usuario_nombre = loan['usuario_nombre_u'] or loan['usuario']

                try:
                    resp = notificaciones_client.enviar_notificacion(
                        tipo="POR_VENCER",
                        usuario=usuario_nombre,
                        correo=correo,
                        datos={
                            "titulo": loan['libro_titulo'] or "",
                            "fecha_limite": fecha_legible,
                            "dias_restantes": dias_restantes
                        },
                        clave=f"POR_VENCER:{loan['id']}:{fecha_legible}"
                    )
                    if resp.status_code == 202:
                        cursor.execute(
                            "UPDATE prestamos SET aviso_enviado_en = ?, aviso_vencimiento_enviado = 1 WHERE id = ?",
                            (datetime.now().isoformat(), loan['id'])
                        )
                        conn.commit()
                        avisados += 1
                    else:
                        logger.warning(f"Notificaciones respondió HTTP {resp.status_code} para préstamo #{loan['id']}")
                except ServicioNoDisponible as err:
                    logger.warning(f"Notificaciones no disponible durante revisión de préstamo #{loan['id']}: {err}")
                    notificaciones_disponible = False
                    break

        # 2. Reintentar multas pendientes de notificación si el servicio sigue disponible
        if notificaciones_disponible:
            cursor.execute("""
                SELECT m.id as multa_id, m.prestamo_id, m.dias_retraso, m.monto,
                       p.libro_titulo, p.usuario as prestamo_usuario,
                       u.correo as usuario_correo, u.nombre as usuario_nombre_u
                FROM multas m
                JOIN prestamos p ON m.prestamo_id = p.id
                LEFT JOIN usuarios u ON (p.usuario_id = u.id OR (p.usuario_id IS NULL AND (u.codigo = p.ci OR u.ci = p.ci)))
                WHERE m.notificada = 0
                ORDER BY m.id ASC
            """)
            multas_pendientes = [dict(row) for row in cursor.fetchall()]

            for m in multas_pendientes:
                correo = (m['usuario_correo'] or '').strip()
                if not correo:
                    continue

                usuario_nombre = m['usuario_nombre_u'] or m['prestamo_usuario']
                try:
                    resp = notificaciones_client.enviar_notificacion(
                        tipo="MULTA",
                        usuario=usuario_nombre,
                        correo=correo,
                        datos={
                            "titulo": m['libro_titulo'] or "",
                            "monto": m['monto'],
                            "dias_retraso": m['dias_retraso']
                        },
                        clave=f"MULTA:{m['prestamo_id']}"
                    )
                    if resp.status_code == 202:
                        cursor.execute(
                            "UPDATE multas SET notificada = 1 WHERE id = ?",
                            (m['multa_id'],)
                        )
                        conn.commit()
                        multas_reenviadas += 1
                    else:
                        logger.warning(f"Notificaciones respondió HTTP {resp.status_code} para multa #{m['multa_id']}")
                except ServicioNoDisponible as err:
                    logger.warning(f"Notificaciones no disponible durante reenvío de multa #{m['multa_id']}: {err}")
                    notificaciones_disponible = False
                    break
    finally:
        conn.close()

    return jsonify({
        "revisados": revisados,
        "avisados": avisados,
        "multas_reenviadas": multas_reenviadas,
        "sin_correo": sin_correo,
        "notificaciones_disponible": notificaciones_disponible
    }), 200

# --- PROXY CATÁLOGO (LIBROS Y AUTORES) ---

@app.route('/libros', methods=['GET', 'POST'])
def proxy_libros():
    if request.method == 'GET':
        try:
            resp = catalogo_client.obtener_libros(params=request.args)
            data = resp.json() if 'application/json' in resp.headers.get('content-type', '') else resp.text
            return jsonify(data), resp.status_code
        except ServicioNoDisponible as e:
            logger.error(f"Error comunicando con Catálogo al obtener libros: {e}")
            return jsonify({"error": "No se pudo comunicar con el servicio de Catálogo"}), 503
    try:
        resp = catalogo_client.crear_libro(request.get_json())
        data = resp.json() if 'application/json' in resp.headers.get('content-type', '') else {"mensaje": resp.text}
        return jsonify(data), resp.status_code
    except ServicioNoDisponible as e:
        logger.error(f"Error comunicando con Catálogo al crear libro: {e}")
        return jsonify({"error": "No se pudo comunicar con el servicio de Catálogo"}), 503

@app.route('/libros/<int:libro_id>', methods=['PUT'])
def proxy_actualizar_libro(libro_id):
    try:
        resp = catalogo_client.actualizar_libro(libro_id, request.get_json())
        data = resp.json() if 'application/json' in resp.headers.get('content-type', '') else {"mensaje": resp.text}
        return jsonify(data), resp.status_code
    except ServicioNoDisponible as e:
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
        resp = catalogo_client.eliminar_libro(libro_id)
        if resp.status_code == 204:
            return '', 204
        data = resp.json() if 'application/json' in resp.headers.get('content-type', '') else {"error": resp.text}
        return jsonify(data), resp.status_code
    except ServicioNoDisponible as e:
        logger.error(f"Error comunicando con Catálogo al eliminar libro {libro_id}: {e}")
        return jsonify({"error": "No se pudo comunicar con el servicio de Catálogo"}), 503

@app.route('/autores', methods=['GET', 'POST'])
def proxy_autores():
    if request.method == 'GET':
        try:
            resp = catalogo_client.obtener_autores(params=request.args)
            data = resp.json() if 'application/json' in resp.headers.get('content-type', '') else resp.text
            return jsonify(data), resp.status_code
        except ServicioNoDisponible as e:
            logger.error(f"Error comunicando con Catálogo al obtener autores: {e}")
            return jsonify({"error": "No se pudo comunicar con el servicio de Catálogo"}), 503
    try:
        resp = catalogo_client.crear_autor(request.get_json())
        data = resp.json() if 'application/json' in resp.headers.get('content-type', '') else {"mensaje": resp.text}
        return jsonify(data), resp.status_code
    except ServicioNoDisponible as e:
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




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8002, debug=True)

