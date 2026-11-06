import re
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from database import get_db_connection

logger = logging.getLogger("prestamos.usuarios")

usuarios_bp = Blueprint('usuarios', __name__)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NOMBRE_REGEX = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s]+$")
TIPOS_VALIDOS = {'ESTUDIANTE', 'DOCENTE'}

# ---------------------------------------------------------------------------
# Funciones auxiliares y lógica de servicio
# ---------------------------------------------------------------------------

def validar_correo(correo: str) -> bool:
    if not correo or not isinstance(correo, str):
        return False
    return bool(EMAIL_REGEX.match(correo.strip()))

def validar_tipo(tipo: str) -> bool:
    if not tipo or not isinstance(tipo, str):
        return False
    return tipo.strip().upper() in TIPOS_VALIDOS

def validar_nombre(nombre: str) -> bool:
    if not nombre or not isinstance(nombre, str):
        return False
    return bool(NOMBRE_REGEX.match(nombre.strip()))

def validar_ci_numerico(ci: str) -> bool:
    if not ci or not isinstance(ci, str):
        return False
    ci_clean = ci.strip()
    return ci_clean.isdigit() and 4 <= len(ci_clean) <= 15

def parse_date_util(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(str(date_str))
    except ValueError:
        try:
            return datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        except Exception:
            return None

def actualizar_usuarios_morosos(conn=None):
    """
    Control de vencimiento y bloqueo por incumplimiento:
    1. VENCIMIENTO: se acabó el plazo, tiene 7 días extras (notifica al vencer el plazo original).
    2. BLOQUEO_POR_INCUMPLIMIENTO: pasaron los 7 días extras y no devolvió (bloquea la cuenta y notifica).
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, usuario_id, ci, usuario, fecha_limite, libro_titulo, fecha_prestamo,
                   notif_vencimiento_enviada, notif_bloqueo_incumplimiento_enviada
            FROM prestamos
            WHERE estado = 'ACTIVO'
        """)
        prestamos_activos = [dict(r) for r in cursor.fetchall()]

        ahora = datetime.now()
        ahora_date = ahora.date()
        deshabilitados = 0
        usuarios_afectados = set()

        for p in prestamos_activos:
            f_lim_str = p.get('fecha_limite')
            f_lim_dt = parse_date_util(f_lim_str)
            if not f_lim_dt:
                continue

            # Calcular días transcurridos desde que venció el plazo
            dias_vencido = (ahora_date - f_lim_dt.date()).days
            if 'T' in str(f_lim_str) and ahora > f_lim_dt and dias_vencido < 1:
                dias_vencido = 1

            u_id = p.get('usuario_id')
            ci = str(p.get('ci') or '').strip()

            # Obtener correo del usuario
            correo_u = ""
            if u_id:
                cursor.execute("SELECT correo, activo FROM usuarios WHERE id = ?", (u_id,))
                r_u = cursor.fetchone()
                if r_u and r_u['correo']:
                    correo_u = str(r_u['correo']).strip()
            if not correo_u and ci:
                cursor.execute("SELECT correo, activo FROM usuarios WHERE ci = ? OR codigo = ?", (ci, ci))
                r_u = cursor.fetchone()
                if r_u and r_u['correo']:
                    correo_u = str(r_u['correo']).strip()

            # CASO A: Pasaron los 7 días extras y no devolvió -> BLOQUEO_POR_INCUMPLIMIENTO
            if dias_vencido > 7:
                # Bloquear usuario
                if u_id:
                    cursor.execute("""
                        UPDATE usuarios 
                        SET activo = 0, bloqueado_motivo = 'INCUMPLIMIENTO'
                        WHERE id = ? AND activo = 1
                    """, (u_id,))
                    if cursor.rowcount > 0:
                        deshabilitados += cursor.rowcount
                        usuarios_afectados.add(f"ID #{u_id} ({p.get('usuario')})")

                if ci:
                    cursor.execute("""
                        UPDATE usuarios 
                        SET activo = 0, bloqueado_motivo = 'INCUMPLIMIENTO'
                        WHERE (ci = ? OR codigo = ?) AND activo = 1
                    """, (ci, ci))
                    if cursor.rowcount > 0:
                        deshabilitados += cursor.rowcount
                        usuarios_afectados.add(f"CI {ci} ({p.get('usuario')})")

                # Enviar notificación BLOQUEO_POR_INCUMPLIMIENTO
                if not p.get('notif_bloqueo_incumplimiento_enviada') and correo_u:
                    try:
                        from clients import NotificacionesClient
                        n_client = NotificacionesClient()
                        f_legible = str(p.get('fecha_limite'))[:10]
                        resp = n_client.enviar_notificacion(
                            tipo="BLOQUEO_POR_INCUMPLIMIENTO",
                            usuario=p.get('usuario') or 'Usuario',
                            correo=correo_u,
                            datos={
                                "titulo": p.get('libro_titulo') or "",
                                "fecha_prestamo": str(p.get('fecha_prestamo') or '')[:10],
                                "fecha_limite": f_legible,
                                "dias_retraso": dias_vencido,
                                "estado_cuenta": "BLOQUEADA_INCUMPLIMIENTO"
                            },
                            clave=f"BLOQUEO_POR_INCUMPLIMIENTO:{p['id']}"
                        )
                        if resp.status_code == 202:
                            cursor.execute("UPDATE prestamos SET notif_bloqueo_incumplimiento_enviada = 1 WHERE id = ?", (p['id'],))
                    except Exception as e_bl:
                        logger.warning(f"Error al enviar BLOQUEO_POR_INCUMPLIMIENTO para préstamo #{p['id']}: {e_bl}")

            # CASO B: Se acabó el plazo original (1 a 7 días de retraso) -> VENCIMIENTO (tiene 7 días extras)
            elif dias_vencido > 0:
                if not p.get('notif_vencimiento_enviada') and correo_u:
                    try:
                        from clients import NotificacionesClient
                        n_client = NotificacionesClient()
                        f_legible = str(p.get('fecha_limite'))[:10]
                        resp = n_client.enviar_notificacion(
                            tipo="VENCIMIENTO",
                            usuario=p.get('usuario') or 'Usuario',
                            correo=correo_u,
                            datos={
                                "titulo": p.get('libro_titulo') or "",
                                "fecha_prestamo": str(p.get('fecha_prestamo') or '')[:10],
                                "fecha_limite": f_legible,
                                "dias_extras": 7,
                                "dias_retraso": dias_vencido
                            },
                            clave=f"VENCIMIENTO:{p['id']}"
                        )
                        if resp.status_code == 202:
                            cursor.execute("UPDATE prestamos SET notif_vencimiento_enviada = 1 WHERE id = ?", (p['id'],))
                    except Exception as e_venc:
                        logger.warning(f"Error al enviar VENCIMIENTO para préstamo #{p['id']}: {e_venc}")

        if deshabilitados > 0:
            conn.commit()
            logger.info(f"Sistema: {deshabilitados} usuario(s) bloqueado(s) por incumplimiento (> 7 días extras): {list(usuarios_afectados)}")

        return deshabilitados
    except Exception as e:
        logger.error(f"Error en actualizar_usuarios_morosos: {e}")
        return 0
    finally:
        if should_close:
            conn.close()

def servicio_listar_usuarios(tipo_filtro=None, q_filtro=None):
    conn = get_db_connection()
    actualizar_usuarios_morosos(conn)
    cursor = conn.cursor()
    query = "SELECT * FROM usuarios WHERE 1=1"
    params = []

    if tipo_filtro:
        query += " AND UPPER(tipo) = ?"
        params.append(tipo_filtro.strip().upper())

    if q_filtro:
        query += " AND (nombre LIKE ? OR codigo LIKE ? OR ci LIKE ? OR carrera LIKE ? OR facultad LIKE ?)"
        pattern = f"%{q_filtro.strip()}%"
        params.extend([pattern, pattern, pattern, pattern, pattern])

    query += " ORDER BY nombre ASC"
    cursor.execute(query, params)
    usuarios = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return usuarios

def servicio_obtener_usuario(usuario_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def servicio_crear_usuario(data: dict):
    # Formato moderno o legado
    raw_ci = data.get('ci') or data.get('codigo') or ''
    ci = str(raw_ci).strip()
    codigo = str(data.get('codigo') or ci).strip()
    nombre = str(data.get('nombre', '')).strip()
    correo = str(data.get('correo', '')).strip()
    tipo_raw = str(data.get('tipo', 'ESTUDIANTE')).strip().upper()
    facultad = str(data.get('facultad', '')).strip()
    carrera = str(data.get('carrera', '')).strip()

    # Validaciones de campos obligatorios
    if not ci:
        return {"error": "El campo de Carnet de Identidad (CI) es obligatorio."}, 400

    # Validación 4: Campo CI solo números
    if not validar_ci_numerico(ci):
        return {"error": "El Carnet de Identidad (CI) debe contener únicamente números (entre 4 y 15 dígitos)."}, 400

    if not nombre:
        return {"error": "El nombre completo del usuario es obligatorio."}, 400

    # Validación 4: Nombre solo letras y espacios, sin caracteres especiales
    if not validar_nombre(nombre):
        return {"error": "El nombre del usuario solo debe contener letras y espacios, sin números ni caracteres especiales."}, 400

    if not correo:
        return {"error": "El correo es obligatorio."}, 400

    if not validar_correo(correo):
        return {"error": "El correo no tiene un formato válido (ejemplo: usuario@universidad.edu)."}, 400

    if not validar_tipo(tipo_raw):
        return {"error": "El campo 'tipo' debe ser 'ESTUDIANTE' o 'DOCENTE'."}, 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Validación 4: Verificar carnets repetidos
    cursor.execute("SELECT id, nombre FROM usuarios WHERE ci = ? OR codigo = ?", (ci, ci))
    existente = cursor.fetchone()
    if existente:
        conn.close()
        return {
            "error": f"Ya existe un usuario registrado con el CI / Carnet {ci} ({existente['nombre']})."
        }, 409

    fecha_registro = datetime.now().isoformat()
    cursor.execute(
        """
        INSERT INTO usuarios (nombre, ci, codigo, correo, tipo, facultad, carrera, activo, fecha_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (nombre, ci, codigo, correo, tipo_raw, facultad, carrera, fecha_registro)
    )
    conn.commit()
    user_id = cursor.lastrowid
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    usuario = dict(cursor.fetchone())
    conn.close()
    return usuario, 201

def servicio_actualizar_usuario(usuario_id: int, data: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "Usuario no encontrado."}, 404

    usuario_actual = dict(row)

    # Actualizar CI / código
    if 'ci' in data or 'codigo' in data:
        nuevo_ci = str(data.get('ci') or data.get('codigo')).strip()
        if not validar_ci_numerico(nuevo_ci):
            conn.close()
            return {"error": "El Carnet de Identidad (CI) debe contener únicamente números (entre 4 y 15 dígitos)."}, 400

        cursor.execute("SELECT id FROM usuarios WHERE (ci = ? OR codigo = ?) AND id != ?", (nuevo_ci, nuevo_ci, usuario_id))
        if cursor.fetchone():
            conn.close()
            return {"error": f"Ya existe otro usuario registrado con el CI / Carnet {nuevo_ci}."}, 409
        nuevo_codigo = nuevo_ci
    else:
        nuevo_ci = usuario_actual.get('ci') or usuario_actual.get('codigo')
        nuevo_codigo = usuario_actual.get('codigo') or nuevo_ci

    # Actualizar Nombre
    if 'nombre' in data:
        nuevo_nombre = str(data['nombre']).strip()
        if not nuevo_nombre:
            conn.close()
            return {"error": "El nombre no puede estar vacío."}, 400
        if not validar_nombre(nuevo_nombre):
            conn.close()
            return {"error": "El nombre solo debe contener letras y espacios, sin números ni caracteres especiales."}, 400
    else:
        nuevo_nombre = usuario_actual['nombre']

    # Actualizar Correo
    if 'correo' in data:
        nuevo_correo = str(data['correo']).strip()
        if not validar_correo(nuevo_correo):
            conn.close()
            return {"error": "El correo no tiene un formato válido."}, 400
    else:
        nuevo_correo = usuario_actual.get('correo', '')

    # Actualizar Tipo
    if 'tipo' in data:
        nuevo_tipo = str(data['tipo']).strip().upper()
        if not validar_tipo(nuevo_tipo):
            conn.close()
            return {"error": "El campo 'tipo' debe ser 'ESTUDIANTE' o 'DOCENTE'."}, 400
    else:
        nuevo_tipo = usuario_actual.get('tipo', 'ESTUDIANTE')

    # Actualizar Facultad y Carrera
    nuevo_facultad = str(data.get('facultad', usuario_actual.get('facultad', ''))).strip()
    nuevo_carrera = str(data.get('carrera', usuario_actual.get('carrera', ''))).strip()

    # Actualizar Estado Activo
    if 'activo' in data:
        nuevo_activo = 1 if data['activo'] in [1, '1', True, 'true', 'ACTIVO'] else 0
    else:
        nuevo_activo = usuario_actual.get('activo', 1)

    cursor.execute(
        """
        UPDATE usuarios
        SET nombre = ?, ci = ?, codigo = ?, correo = ?, tipo = ?, facultad = ?, carrera = ?, activo = ?
        WHERE id = ?
        """,
        (nuevo_nombre, nuevo_ci, nuevo_codigo, nuevo_correo, nuevo_tipo, nuevo_facultad, nuevo_carrera, nuevo_activo, usuario_id)
    )
    conn.commit()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    usuario_actualizado = dict(cursor.fetchone())
    conn.close()
    return usuario_actualizado, 200

def servicio_reincorporar_usuario(usuario_id: int):
    """Reincorpora a un usuario previamente dado de baja (Requerimiento 3)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "Usuario no encontrado."}, 404

    user = dict(row)
    codigo_val = user.get('codigo') or ''
    ci_val = user.get('ci') or ''

    # Verificar que el usuario no tenga préstamos vencidos aún sin devolver
    cursor.execute("""
        SELECT id, libro_titulo, fecha_limite
        FROM prestamos
        WHERE (usuario_id = ? OR ci = ? OR ci = ?) AND estado = 'ACTIVO'
    """, (usuario_id, codigo_val, ci_val))
    prestamos_activos = [dict(r) for r in cursor.fetchall()]

    ahora = datetime.now()
    ahora_date = ahora.date()
    vencidos = []
    for p in prestamos_activos:
        f_lim_dt = parse_date_util(p.get('fecha_limite'))
        if f_lim_dt:
            if 'T' in str(p.get('fecha_limite')):
                if ahora > f_lim_dt:
                    vencidos.append(p.get('libro_titulo') or f"Préstamo #{p['id']}")
            else:
                if ahora_date > f_lim_dt.date():
                    vencidos.append(p.get('libro_titulo') or f"Préstamo #{p['id']}")

    if vencidos:
        conn.close()
        titulos_str = ", ".join(f'"{t}"' for t in vencidos)
        return {
            "error": f"No se puede reincorporar al usuario: tiene {len(vencidos)} libro(s) con tiempo de entrega vencido sin devolver ({titulos_str}). Debe registrar la devolución de los ejemplares antes de reactivar al usuario."
        }, 409

    cursor.execute("UPDATE usuarios SET activo = 1, bloqueado_motivo = '' WHERE id = ?", (usuario_id,))
    conn.commit()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    usuario = dict(cursor.fetchone())
    conn.close()
    return usuario, 200

def servicio_dar_baja_usuario(usuario_id: int):
    """
    Da de baja a un usuario (Requerimientos 3 y 14).
    Verifica que no posea préstamos ACTIVOS.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "Usuario no encontrado."}, 404

    user = dict(row)
    codigo_val = user.get('codigo') or ''
    ci_val = user.get('ci') or ''
    cursor.execute(
        """
        SELECT COUNT(*) as count 
        FROM prestamos 
        WHERE (usuario_id = ? OR ci = ? OR ci = ?) AND estado = 'ACTIVO'
        """,
        (user['id'], codigo_val, ci_val)
    )
    activos = cursor.fetchone()['count']
    if activos > 0:
        conn.close()
        return {
            "error": f"No se puede dar de baja: el usuario '{user['nombre']}' tiene {activos} préstamo(s) activo(s) en curso. Debe registrar la devolución de los libros antes de darlo de baja."
        }, 409

    cursor.execute("UPDATE usuarios SET activo = 0 WHERE id = ?", (usuario_id,))
    conn.commit()
    conn.close()
    return {"mensaje": f"El usuario '{user['nombre']}' ha sido dado de baja exitosamente.", "activo": 0}, 200


# ---------------------------------------------------------------------------
# Rutas del Blueprint
# ---------------------------------------------------------------------------

@usuarios_bp.route('/usuarios', methods=['GET'])
@usuarios_bp.route('/usuarios/', methods=['GET'])
def listar_usuarios():
    tipo = request.args.get('tipo')
    q = request.args.get('q')
    usuarios = servicio_listar_usuarios(tipo_filtro=tipo, q_filtro=q)
    return jsonify(usuarios), 200

@usuarios_bp.route('/usuarios/<int:usuario_id>', methods=['GET'])
def obtener_usuario(usuario_id):
    usuario = servicio_obtener_usuario(usuario_id)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado."}), 404
    return jsonify(usuario), 200

@usuarios_bp.route('/usuarios', methods=['POST'])
@usuarios_bp.route('/usuarios/', methods=['POST'])
def crear_usuario():
    data = request.get_json() or {}
    res, status = servicio_crear_usuario(data)
    return jsonify(res), status

@usuarios_bp.route('/usuarios/<int:usuario_id>', methods=['PUT', 'PATCH'])
def actualizar_usuario(usuario_id):
    data = request.get_json() or {}
    res, status = servicio_actualizar_usuario(usuario_id, data)
    return jsonify(res), status

@usuarios_bp.route('/usuarios/<int:usuario_id>/reincorporar', methods=['POST', 'PUT'])
def reincorporar_usuario(usuario_id):
    res, status = servicio_reincorporar_usuario(usuario_id)
    return jsonify(res), status

@usuarios_bp.route('/usuarios/<int:usuario_id>', methods=['DELETE'])
def eliminar_usuario(usuario_id):
    res, status = servicio_dar_baja_usuario(usuario_id)
    return jsonify(res), status
