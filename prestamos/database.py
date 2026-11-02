import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "/data/prestamos.db")

def get_db_connection():
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
        CREATE TABLE IF NOT EXISTS prestamos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            libro_id INTEGER NOT NULL,
            fecha_prestamo TEXT NOT NULL,
            fecha_limite TEXT NOT NULL,
            fecha_devolucion TEXT,
            estado TEXT NOT NULL DEFAULT 'ACTIVO',
            aviso_vencimiento_enviado INTEGER NOT NULL DEFAULT 0,
            ci TEXT
        )
    ''')

    # Migrate databases created before reminder deduplication was introduced.
    cursor.execute("PRAGMA table_info(prestamos)")
    columnas = {row[1] for row in cursor.fetchall()}
    if 'aviso_vencimiento_enviado' not in columnas:
        cursor.execute(
            "ALTER TABLE prestamos ADD COLUMN aviso_vencimiento_enviado "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if 'ci' not in columnas:
        cursor.execute("ALTER TABLE prestamos ADD COLUMN ci TEXT")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS multas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prestamo_id INTEGER NOT NULL,
            dias_retraso INTEGER NOT NULL,
            monto REAL NOT NULL,
            estado TEXT NOT NULL DEFAULT 'PENDIENTE',
            FOREIGN KEY (prestamo_id) REFERENCES prestamos (id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ci TEXT NOT NULL UNIQUE,
            fecha_registro TEXT NOT NULL
        )
    ''')

    # Poblar con usuarios que ya tengan préstamos registrados
    cursor.execute("""
        INSERT OR IGNORE INTO usuarios (nombre, ci, fecha_registro)
        SELECT DISTINCT usuario, ci, MIN(fecha_prestamo)
        FROM prestamos
        WHERE usuario IS NOT NULL AND ci IS NOT NULL AND TRIM(ci) != ''
        GROUP BY ci
    """)
    
    conn.commit()
    conn.close()
