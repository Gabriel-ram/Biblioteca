import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "/data/catalogo.db")

def get_db_connection():
    # Ensure directory exists before connecting
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS autores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            nacionalidad TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS libros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            autor_id INTEGER,
            ejemplares_totales INTEGER NOT NULL DEFAULT 1,
            ejemplares_disponibles INTEGER NOT NULL DEFAULT 1,
            estado TEXT NOT NULL DEFAULT 'DISPONIBLE',
            FOREIGN KEY (autor_id) REFERENCES autores (id) ON DELETE SET NULL
        )
    ''')

    # Deduplicar autores existentes y reasignar libros al primer autor
    cursor.execute('''
        SELECT MIN(id) as keeper_id, LOWER(TRIM(nombre)) as norm_name
        FROM autores
        GROUP BY LOWER(TRIM(nombre))
        HAVING COUNT(*) > 1
    ''')
    dup_groups = cursor.fetchall()
    for row in dup_groups:
        keeper_id = row['keeper_id']
        norm_name = row['norm_name']
        cursor.execute("SELECT id FROM autores WHERE LOWER(TRIM(nombre)) = ? AND id != ?", (norm_name, keeper_id))
        dup_rows = cursor.fetchall()
        for dup in dup_rows:
            dup_id = dup['id']
            cursor.execute("UPDATE libros SET autor_id = ? WHERE autor_id = ?", (keeper_id, dup_id))
            cursor.execute("DELETE FROM autores WHERE id = ?", (dup_id,))

    # Deduplicar libros existentes (mismo título normalizado y autor) consolidando ejemplares
    cursor.execute('''
        SELECT MIN(id) as keeper_id, LOWER(TRIM(titulo)) as norm_title, COALESCE(autor_id, 0) as norm_autor
        FROM libros
        GROUP BY LOWER(TRIM(titulo)), COALESCE(autor_id, 0)
        HAVING COUNT(*) > 1
    ''')
    dup_libros_groups = cursor.fetchall()
    for row in dup_libros_groups:
        keeper_id = row['keeper_id']
        norm_title = row['norm_title']
        norm_autor = row['norm_autor']
        if norm_autor == 0:
            cursor.execute("SELECT id, ejemplares_totales, ejemplares_disponibles FROM libros WHERE LOWER(TRIM(titulo)) = ? AND autor_id IS NULL AND id != ?", (norm_title, keeper_id))
        else:
            cursor.execute("SELECT id, ejemplares_totales, ejemplares_disponibles FROM libros WHERE LOWER(TRIM(titulo)) = ? AND autor_id = ? AND id != ?", (norm_title, norm_autor, keeper_id))
        dup_rows = cursor.fetchall()
        extra_tot = sum(d['ejemplares_totales'] for d in dup_rows)
        extra_disp = sum(d['ejemplares_disponibles'] for d in dup_rows)
        cursor.execute("UPDATE libros SET ejemplares_totales = ejemplares_totales + ?, ejemplares_disponibles = ejemplares_disponibles + ? WHERE id = ?", (extra_tot, extra_disp, keeper_id))
        cursor.execute("UPDATE libros SET estado = CASE WHEN ejemplares_disponibles > 0 THEN 'DISPONIBLE' ELSE 'AGOTADO' END WHERE id = ?", (keeper_id,))
        for dup in dup_rows:
            cursor.execute("DELETE FROM libros WHERE id = ?", (dup['id'],))

    # Índice único para garantizar que no se inserten libros duplicados por autor
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_libros_titulo_autor
        ON libros(LOWER(TRIM(titulo)), COALESCE(autor_id, 0))
    ''')

    conn.commit()
    conn.close()
