import re
from flask import Flask, request, jsonify
from database import init_db, get_db_connection

app = Flask(__name__)

# Initialize Database tables on application startup
with app.app_context():
    init_db()

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "UP"}), 200

# --- AUTORES ENDPOINTS ---

@app.route('/autores', methods=['POST'])
def crear_autor():
    data = request.get_json() or {}
    nombre = data.get('nombre')
    nacionalidad = data.get('nacionalidad', '')
    area = data.get('area', '')

    if not nombre or not str(nombre).strip():
        return jsonify({"error": "El campo 'nombre' del autor es obligatorio."}), 400

    nombre = str(nombre).strip()
    nacionalidad = str(nacionalidad).strip()
    area = str(area).strip()

    # Validar nombre: solo letras, espacios, acentos, puntos y guiones
    if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\.\-]+$", nombre):
        return jsonify({"error": "El nombre del autor solo puede contener letras, espacios, acentos, puntos y guiones."}), 400

    if not nacionalidad:
        return jsonify({"error": "La nacionalidad del autor es obligatoria."}), 400

    if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\(\)\.\-]+$", nacionalidad):
        return jsonify({"error": "La nacionalidad del autor solo debe contener letras y espacios."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM autores WHERE LOWER(TRIM(nombre)) = LOWER(?)", (nombre,))
    existente = cursor.fetchone()
    if existente:
        conn.close()
        return jsonify({
            "error": f"Ya existe un autor registrado con el nombre '{nombre}'."
        }), 409

    cursor.execute(
        "INSERT INTO autores (nombre, nacionalidad, area) VALUES (?, ?, ?)",
        (nombre, nacionalidad, area)
    )
    conn.commit()
    autor_id = cursor.lastrowid
    
    cursor.execute("SELECT * FROM autores WHERE id = ?", (autor_id,))
    autor = dict(cursor.fetchone())
    conn.close()

    return jsonify(autor), 201

@app.route('/autores', methods=['GET'])
def listar_autores():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM autores ORDER BY nombre ASC")
    autores = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(autores), 200

@app.route('/autores/<int:autor_id>', methods=['PUT'])
def actualizar_autor(autor_id):
    data = request.get_json() or {}
    nombre = data.get('nombre')
    nacionalidad = data.get('nacionalidad')
    area = data.get('area', '')

    if not nombre or not str(nombre).strip():
        return jsonify({"error": "El nombre del autor es obligatorio."}), 400

    nombre = str(nombre).strip()
    nacionalidad = str(nacionalidad or '').strip()
    area = str(area or '').strip()

    if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\.\-]+$", nombre):
        return jsonify({"error": "El nombre del autor solo puede contener letras, espacios, acentos, puntos y guiones."}), 400

    if not nacionalidad:
        return jsonify({"error": "La nacionalidad del autor es obligatoria."}), 400

    if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\(\)\.\-]+$", nacionalidad):
        return jsonify({"error": "La nacionalidad del autor solo debe contener letras y espacios."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM autores WHERE id = ?", (autor_id,))
    autor = cursor.fetchone()
    if not autor:
        conn.close()
        return jsonify({"error": "Autor no encontrado."}), 404

    # Verificar que el nuevo nombre no choque con otro autor existente
    cursor.execute("SELECT * FROM autores WHERE LOWER(TRIM(nombre)) = LOWER(?) AND id != ?", (nombre, autor_id))
    existente = cursor.fetchone()
    if existente:
        conn.close()
        return jsonify({
            "error": f"Ya existe otro autor registrado con el nombre '{nombre}'."
        }), 409

    cursor.execute(
        "UPDATE autores SET nombre = ?, nacionalidad = ?, area = ? WHERE id = ?",
        (nombre, nacionalidad, area, autor_id)
    )
    conn.commit()

    cursor.execute("SELECT * FROM autores WHERE id = ?", (autor_id,))
    autor_actualizado = dict(cursor.fetchone())
    conn.close()

    return jsonify(autor_actualizado), 200

# --- LIBROS ENDPOINTS ---

@app.route('/libros', methods=['POST'])
def crear_libro():
    data = request.get_json() or {}
    titulo = data.get('titulo')
    autor_id = data.get('autor_id')
    genero = data.get('genero')
    edicion = data.get('edicion', '')
    ejemplares_totales = data.get('ejemplares_totales', 1)
    sumar_si_existe = data.get('sumar_si_existe', False) or (request.args.get('sumar_si_existe') in ['true', '1'])

    if not titulo:
        return jsonify({"error": "El campo 'titulo' es obligatorio."}), 400

    titulo = str(titulo).strip()
    if not titulo:
        return jsonify({"error": "El campo 'titulo' no puede estar vacío."}), 400

    # Asignación de autor OBLIGATORIA (Requerimiento 5)
    if autor_id is None or str(autor_id).strip() == '':
        return jsonify({"error": "La asignación de un autor es obligatoria para registrar un libro."}), 400

    try:
        autor_id = int(autor_id)
    except (ValueError, TypeError):
        return jsonify({"error": "El campo 'autor_id' debe ser un número entero válido."}), 400

    # Género OBLIGATORIO (Requerimiento 6)
    if not genero or not str(genero).strip():
        return jsonify({"error": "El género del libro es obligatorio. Seleccione una categoría universitaria."}), 400
    genero = str(genero).strip()

    edicion = str(edicion).strip() if edicion else ''

    try:
        ejemplares_totales = int(ejemplares_totales)
    except (ValueError, TypeError):
        return jsonify({"error": "'ejemplares_totales' debe ser un número entero."}), 400

    if ejemplares_totales < 1:
        return jsonify({"error": "'ejemplares_totales' debe ser mayor o igual a 1."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM autores WHERE id = ?", (autor_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": f"El autor con ID {autor_id} no existe."}), 404

    # Comprobar si ya existe un libro con el mismo título y autor
    cursor.execute(
        "SELECT * FROM libros WHERE LOWER(TRIM(titulo)) = LOWER(?) AND autor_id = ?",
        (titulo, autor_id)
    )
    existente = cursor.fetchone()

    if existente:
        existente_dict = dict(existente)
        if sumar_si_existe:
            nuevos_totales = existente_dict['ejemplares_totales'] + ejemplares_totales
            nuevos_disp = existente_dict['ejemplares_disponibles'] + ejemplares_totales
            nuevo_estado = 'DISPONIBLE' if nuevos_disp > 0 else 'AGOTADO'
            cursor.execute(
                """
                UPDATE libros
                SET ejemplares_totales = ?, ejemplares_disponibles = ?, estado = ?, genero = ?, edicion = ?
                WHERE id = ?
                """,
                (nuevos_totales, nuevos_disp, nuevo_estado, genero, edicion, existente_dict['id'])
            )
            conn.commit()
            cursor.execute("SELECT * FROM libros WHERE id = ?", (existente_dict['id'],))
            libro = dict(cursor.fetchone())
            conn.close()
            return jsonify(libro), 200
        else:
            conn.close()
            return jsonify({
                "error": f"Ya existe una obra registrada con el título '{existente_dict['titulo']}' para este autor (ID: {existente_dict['id']}).",
                "libro_existente": existente_dict,
                "sugerencia": "Para añadir más unidades, modifica los ejemplares del libro existente o utiliza 'sumar_si_existe: true'."
            }), 409

    ejemplares_disponibles = max(0, ejemplares_totales)
    estado = 'DISPONIBLE' if ejemplares_disponibles > 0 else 'AGOTADO'

    cursor.execute(
        """
        INSERT INTO libros (titulo, autor_id, genero, edicion, ejemplares_totales, ejemplares_disponibles, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (titulo, autor_id, genero, edicion, ejemplares_totales, ejemplares_disponibles, estado)
    )
    conn.commit()
    libro_id = cursor.lastrowid

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    libro = dict(cursor.fetchone())
    conn.close()

    return jsonify(libro), 201

@app.route('/libros', methods=['GET'])
def listar_libros():
    disponible_param = request.args.get('disponible')
    
    conn = get_db_connection()
    cursor = conn.cursor()

    if disponible_param and disponible_param.lower() in ['true', '1']:
        cursor.execute("SELECT * FROM libros WHERE ejemplares_disponibles > 0 AND estado = 'DISPONIBLE'")
    else:
        cursor.execute("SELECT * FROM libros")

    libros = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(libros), 200

@app.route('/libros/<int:libro_id>', methods=['GET'])
def obtener_libro(libro_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Libro no encontrado"}), 404

    return jsonify(dict(row)), 200

@app.route('/libros/<int:libro_id>', methods=['PUT'])
def actualizar_libro(libro_id):
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Libro no encontrado"}), 404

    libro_actual = dict(row)
    titulo = data.get('titulo', libro_actual['titulo'])
    autor_id = data.get('autor_id', libro_actual['autor_id'])
    genero = data.get('genero', libro_actual.get('genero', 'General'))
    edicion = data.get('edicion', libro_actual.get('edicion', ''))

    if autor_id is not None:
        cursor.execute("SELECT id FROM autores WHERE id = ?", (autor_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({"error": f"El autor con ID {autor_id} no existe"}), 400

    titulo_norm = str(titulo).strip()
    if autor_id is not None:
        cursor.execute(
            "SELECT id, titulo FROM libros WHERE LOWER(TRIM(titulo)) = LOWER(?) AND autor_id = ? AND id != ?",
            (titulo_norm, autor_id, libro_id)
        )
    else:
        cursor.execute(
            "SELECT id, titulo FROM libros WHERE LOWER(TRIM(titulo)) = LOWER(?) AND autor_id IS NULL AND id != ?",
            (titulo_norm, libro_id)
        )
    colision = cursor.fetchone()
    if colision:
        conn.close()
        return jsonify({
            "error": f"Ya existe otro libro con el título '{colision['titulo']}' para este autor (ID: {colision['id']})"
        }), 409

    total_anterior = libro_actual['ejemplares_totales']
    disponibles_anterior = libro_actual['ejemplares_disponibles']
    prestados = total_anterior - disponibles_anterior

    if 'ejemplares_totales' in data:
        raw_totales = data['ejemplares_totales']
        if isinstance(raw_totales, bool) or raw_totales is None:
            conn.close()
            return jsonify({"error": "'ejemplares_totales' debe ser un número entero mayor o igual a 1"}), 400
        try:
            nuevo_total = int(raw_totales)
            if isinstance(raw_totales, float) and not raw_totales.is_integer():
                conn.close()
                return jsonify({"error": "'ejemplares_totales' debe ser un número entero"}), 400
        except (ValueError, TypeError):
            conn.close()
            return jsonify({"error": "'ejemplares_totales' debe ser un número entero"}), 400

        if nuevo_total < 1:
            conn.close()
            return jsonify({"error": "'ejemplares_totales' debe ser mayor o igual a 1"}), 400

        if nuevo_total < prestados:
            conn.close()
            return jsonify({
                "error": f"No se puede reducir el total a {nuevo_total} porque hay {prestados} ejemplares prestados"
            }), 409

        ejemplares_totales = nuevo_total
        ejemplares_disponibles = nuevo_total - prestados
    else:
        ejemplares_totales = total_anterior
        ejemplares_disponibles = disponibles_anterior

    estado_param = data.get('estado')
    if estado_param in ['DISPONIBLE', 'AGOTADO', 'INACTIVO']:
        estado = estado_param
    elif libro_actual.get('estado') == 'INACTIVO':
        estado = 'INACTIVO'
    else:
        estado = 'DISPONIBLE' if ejemplares_disponibles > 0 else 'AGOTADO'

    cursor.execute(
        """
        UPDATE libros
        SET titulo = ?, autor_id = ?, genero = ?, edicion = ?, ejemplares_totales = ?, ejemplares_disponibles = ?, estado = ?
        WHERE id = ?
        """,
        (titulo_norm, autor_id, genero, edicion, ejemplares_totales, ejemplares_disponibles, estado, libro_id)
    )
    conn.commit()

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    libro_actualizado = dict(cursor.fetchone())
    conn.close()

    return jsonify(libro_actualizado), 200

@app.route('/libros/<int:libro_id>/reincorporar', methods=['POST', 'PUT'])
def reincorporar_libro(libro_id):
    """Reactiva un libro que fue pasado a estado INACTIVO (Requerimiento 7)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Libro no encontrado"}), 404

    libro = dict(row)
    nuevo_estado = 'DISPONIBLE' if libro['ejemplares_disponibles'] > 0 else 'AGOTADO'

    cursor.execute("UPDATE libros SET estado = ? WHERE id = ?", (nuevo_estado, libro_id))
    conn.commit()

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    actualizado = dict(cursor.fetchone())
    conn.close()
    return jsonify(actualizado), 200

@app.route('/libros/<int:libro_id>', methods=['DELETE'])
def eliminar_libro(libro_id):
    """
    Requerimiento 7 y 14:
    Si el libro tiene ejemplares prestados (disponibles < totales), responde 409 Conflict.
    Si no tiene préstamos activos, no se borra la fila física para preservar historial,
    sino que pasa a estado 'INACTIVO'.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Libro no encontrado"}), 404

    libro = dict(row)
    prestados = libro['ejemplares_totales'] - libro['ejemplares_disponibles']
    if prestados > 0:
        conn.close()
        return jsonify({
            "error": f"No se puede dar de baja el libro '{libro['titulo']}': tiene {prestados} ejemplar(es) actualmente en préstamo. Registre la devolución antes de darlo de baja."
        }), 409

    cursor.execute("UPDATE libros SET estado = 'INACTIVO' WHERE id = ?", (libro_id,))
    conn.commit()
    conn.close()

    return jsonify({
        "mensaje": f"El libro '{libro['titulo']}' ha sido marcado como INACTIVO exitosamente.",
        "estado": "INACTIVO"
    }), 200

@app.route('/libros/<int:libro_id>/disponibilidad', methods=['PATCH'])
def cambiar_disponibilidad(libro_id):
    data = request.get_json() or {}
    operacion = data.get('operacion')

    if operacion not in ['descontar', 'reponer']:
        return jsonify({"error": "Operación inválida. Debe ser 'descontar' o 'reponer'"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    if operacion == 'descontar':
        cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Libro no encontrado"}), 404
        
        libro = dict(row)
        if libro['estado'] == 'INACTIVO':
            conn.close()
            return jsonify({"error": f"El libro '{libro['titulo']}' se encuentra INACTIVO y no puede prestarse."}), 409

        if libro['ejemplares_disponibles'] <= 0:
            conn.close()
            return jsonify({"error": f"El libro '{libro['titulo']}' no cuenta con ejemplares disponibles."}), 409

        cursor.execute(
            """
            UPDATE libros
            SET ejemplares_disponibles = ejemplares_disponibles - 1,
                estado = CASE WHEN ejemplares_disponibles - 1 = 0 THEN 'AGOTADO' ELSE 'DISPONIBLE' END
            WHERE id = ? AND ejemplares_disponibles > 0
            """,
            (libro_id,)
        )

    elif operacion == 'reponer':
        cursor.execute(
            """
            UPDATE libros
            SET ejemplares_disponibles = ejemplares_disponibles + 1,
                estado = CASE WHEN estado = 'INACTIVO' THEN 'INACTIVO' ELSE 'DISPONIBLE' END
            WHERE id = ? AND ejemplares_disponibles < ejemplares_totales
            """,
            (libro_id,)
        )
        if cursor.rowcount == 0:
            cursor.execute("SELECT id FROM libros WHERE id = ?", (libro_id,))
            if not cursor.fetchone():
                conn.close()
                return jsonify({"error": "Libro no encontrado"}), 404
            conn.close()
            return jsonify({"error": "Todos los ejemplares ya están disponibles"}), 409

    conn.commit()

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    libro_actualizado = dict(cursor.fetchone())
    conn.close()

    return jsonify(libro_actualizado), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8001, debug=True)
