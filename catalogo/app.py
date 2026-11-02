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

    if not nombre:
        return jsonify({"error": "El campo 'nombre' es obligatorio"}), 400

    nombre = str(nombre).strip()
    nacionalidad = str(nacionalidad).strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM autores WHERE LOWER(TRIM(nombre)) = LOWER(?)", (nombre,))
    existente = cursor.fetchone()
    if existente:
        autor = dict(existente)
        conn.close()
        return jsonify(autor), 200

    cursor.execute(
        "INSERT INTO autores (nombre, nacionalidad) VALUES (?, ?)",
        (nombre, nacionalidad)
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
    cursor.execute("SELECT * FROM autores")
    autores = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(autores), 200

# --- LIBROS ENDPOINTS ---

@app.route('/libros', methods=['POST'])
def crear_libro():
    data = request.get_json() or {}
    titulo = data.get('titulo')
    autor_id = data.get('autor_id')
    ejemplares_totales = data.get('ejemplares_totales', 1)

    if not titulo:
        return jsonify({"error": "El campo 'titulo' es obligatorio"}), 400

    try:
        ejemplares_totales = int(ejemplares_totales)
    except (ValueError, TypeError):
        return jsonify({"error": "'ejemplares_totales' debe ser un número entero"}), 400

    ejemplares_disponibles = max(0, ejemplares_totales)
    estado = 'DISPONIBLE' if ejemplares_disponibles > 0 else 'AGOTADO'

    conn = get_db_connection()
    cursor = conn.cursor()

    if autor_id is not None:
        cursor.execute("SELECT id FROM autores WHERE id = ?", (autor_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({"error": f"El autor con ID {autor_id} no existe"}), 400

    cursor.execute(
        """
        INSERT INTO libros (titulo, autor_id, ejemplares_totales, ejemplares_disponibles, estado)
        VALUES (?, ?, ?, ?, ?)
        """,
        (titulo, autor_id, ejemplares_totales, ejemplares_disponibles, estado)
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
    ejemplares_totales = data.get('ejemplares_totales', libro_actual['ejemplares_totales'])
    ejemplares_disponibles = data.get('ejemplares_disponibles', libro_actual['ejemplares_disponibles'])
    
    estado = 'DISPONIBLE' if ejemplares_disponibles > 0 else 'AGOTADO'

    cursor.execute(
        """
        UPDATE libros
        SET titulo = ?, autor_id = ?, ejemplares_totales = ?, ejemplares_disponibles = ?, estado = ?
        WHERE id = ?
        """,
        (titulo, autor_id, ejemplares_totales, ejemplares_disponibles, estado, libro_id)
    )
    conn.commit()

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    libro_actualizado = dict(cursor.fetchone())
    conn.close()

    return jsonify(libro_actualizado), 200

@app.route('/libros/<int:libro_id>', methods=['DELETE'])
def eliminar_libro(libro_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Libro no encontrado"}), 404

    cursor.execute("DELETE FROM libros WHERE id = ?", (libro_id,))
    conn.commit()
    conn.close()

    return '', 204

@app.route('/libros/<int:libro_id>/disponibilidad', methods=['PATCH'])
def cambiar_disponibilidad(libro_id):
    data = request.get_json() or {}
    operacion = data.get('operacion')

    if operacion not in ['descontar', 'reponer']:
        return jsonify({"error": "Operación inválida. Debe ser 'descontar' o 'reponer'"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Libro no encontrado"}), 404

    libro = dict(row)
    disponibles = libro['ejemplares_disponibles']

    if operacion == 'descontar':
        if disponibles <= 0:
            conn.close()
            return jsonify({"error": "Libro no disponible"}), 409
        
        nuevos_disponibles = disponibles - 1
        nuevo_estado = 'AGOTADO' if nuevos_disponibles == 0 else 'DISPONIBLE'

    elif operacion == 'reponer':
        nuevos_disponibles = disponibles + 1
        nuevo_estado = 'DISPONIBLE'

    cursor.execute(
        """
        UPDATE libros
        SET ejemplares_disponibles = ?, estado = ?
        WHERE id = ?
        """,
        (nuevos_disponibles, nuevo_estado, libro_id)
    )
    conn.commit()

    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    libro_actualizado = dict(cursor.fetchone())
    conn.close()

    return jsonify(libro_actualizado), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8001, debug=True)
