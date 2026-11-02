import re
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from database import get_db_connection

logger = logging.getLogger("prestamos.usuarios")

usuarios_bp = Blueprint('usuarios', __name__)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
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

def servicio_listar_usuarios(tipo_filtro=None, q_filtro=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM usuarios WHERE 1=1"
    params = []

    if tipo_filtro:
        query += " AND UPPER(tipo) = ?"
        params.append(tipo_filtro.strip().upper())

    if q_filtro:
        query += " AND (nombre LIKE ? OR codigo LIKE ?)"
        pattern = f"%{q_filtro.strip()}%"
        params.extend([pattern, pattern])

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
    # Detección de formato: nuevo {codigo, nombre, correo, tipo} vs legado {nombre, ci}
    tiene_codigo = 'codigo' in data

    if tiene_codigo:
        codigo = str(data.get('codigo', '')).strip()
        nombre = str(data.get('nombre', '')).strip()
        correo = str(data.get('correo', '')).strip()
        tipo_raw = str(data.get('tipo', '')).strip().upper()

        if not codigo or not nombre or not correo or not tipo_raw:
            return {"error": "Los campos 'codigo', 'nombre', 'correo' y 'tipo' son obligatorios"}, 400

        if not validar_correo(correo):
            return {"error": "El correo no tiene un formato válido"}, 400

        if not validar_tipo(tipo_raw):
            return {"error": "El campo 'tipo' debe ser 'ESTUDIANTE' o 'DOCENTE'"}, 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE codigo = ?", (codigo,))
        if cursor.fetchone():
            conn.close()
            return {"error": f"Ya existe un usuario registrado con el código {codigo}"}, 409

        ci = str(data.get('ci', codigo)).strip()
        fecha_registro = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO usuarios (nombre, ci, codigo, correo, tipo, activo, fecha_registro)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (nombre, ci, codigo, correo, tipo_raw, fecha_registro)
        )
        conn.commit()
        user_id = cursor.lastrowid
        cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
        usuario = dict(cursor.fetchone())
        conn.close()
        return usuario, 201

    else:
        # Formato legado {nombre, ci}
        nombre = str(data.get('nombre', '')).strip()
        ci = str(data.get('ci', '')).strip()

        if not nombre or not ci:
            return {"error": "Los campos 'nombre' y 'ci' son obligatorios"}, 400
        if not ci.isascii() or not ci.isdigit() or len(ci) > 8:
            return {"error": "El CI debe contener solo números y tener como máximo 8 dígitos"}, 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE ci = ? OR codigo = ?", (ci, ci))
        if cursor.fetchone():
            conn.close()
            return {"error": f"Ya existe un usuario registrado con el CI {ci}"}, 409

        fecha_registro = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO usuarios (nombre, ci, codigo, correo, tipo, activo, fecha_registro)
            VALUES (?, ?, ?, '', 'ESTUDIANTE', 1, ?)
            """,
            (nombre, ci, ci, fecha_registro)
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
        return {"error": "Usuario no encontrado"}, 404

    usuario_actual = dict(row)

    if 'codigo' in data:
        nuevo_codigo = str(data['codigo']).strip()
        if not nuevo_codigo:
            conn.close()
            return {"error": "El campo 'codigo' no puede estar vacío"}, 400
        cursor.execute("SELECT id FROM usuarios WHERE codigo = ? AND id != ?", (nuevo_codigo, usuario_id))
        if cursor.fetchone():
            conn.close()
            return {"error": f"Ya existe otro usuario con el código {nuevo_codigo}"}, 409
    else:
        nuevo_codigo = usuario_actual['codigo']

    if 'correo' in data:
        nuevo_correo = str(data['correo']).strip()
        if not validar_correo(nuevo_correo):
            conn.close()
            return {"error": "El correo no tiene un formato válido"}, 400
    else:
        nuevo_correo = usuario_actual['correo']

    if 'tipo' in data:
        nuevo_tipo = str(data['tipo']).strip().upper()
        if not validar_tipo(nuevo_tipo):
            conn.close()
            return {"error": "El campo 'tipo' debe ser 'ESTUDIANTE' o 'DOCENTE'"}, 400
    else:
        nuevo_tipo = usuario_actual['tipo']

    if 'nombre' in data:
        nuevo_nombre = str(data['nombre']).strip()
        if not nuevo_nombre:
            conn.close()
            return {"error": "El campo 'nombre' no puede estar vacío"}, 400
    else:
        nuevo_nombre = usuario_actual['nombre']

    nuevo_activo = 1 if data.get('activo', usuario_actual.get('activo', 1)) else 0

    cursor.execute(
        """
        UPDATE usuarios
        SET nombre = ?, codigo = ?, correo = ?, tipo = ?, activo = ?
        WHERE id = ?
        """,
        (nuevo_nombre, nuevo_codigo, nuevo_correo, nuevo_tipo, nuevo_activo, usuario_id)
    )
    conn.commit()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    usuario_actualizado = dict(cursor.fetchone())
    conn.close()
    return usuario_actualizado, 200

def servicio_dar_baja_usuario(usuario_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "Usuario no encontrado"}, 404

    user = dict(row)
    # Verificar préstamos activos asociados por id, codigo o ci
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
            "error": f"No se puede dar de baja: el usuario tiene {activos} préstamo(s) activo(s) en curso."
        }, 409

    cursor.execute("UPDATE usuarios SET activo = 0 WHERE id = ?", (usuario_id,))
    conn.commit()
    conn.close()
    return None, 204


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
        return jsonify({"error": "Usuario no encontrado"}), 404
    return jsonify(usuario), 200

@usuarios_bp.route('/usuarios', methods=['POST'])
@usuarios_bp.route('/usuarios/', methods=['POST'])
def crear_usuario():
    data = request.get_json() or {}
    res, status = servicio_crear_usuario(data)
    return jsonify(res), status

@usuarios_bp.route('/usuarios/<int:usuario_id>', methods=['PUT'])
def actualizar_usuario(usuario_id):
    data = request.get_json() or {}
    res, status = servicio_actualizar_usuario(usuario_id, data)
    return jsonify(res), status

@usuarios_bp.route('/usuarios/<int:usuario_id>', methods=['DELETE'])
def eliminar_usuario(usuario_id):
    res, status = servicio_dar_baja_usuario(usuario_id)
    if status == 204:
        return '', 204
    return jsonify(res), status

