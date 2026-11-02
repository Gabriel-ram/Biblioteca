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

    conn.commit()
    conn.close()
