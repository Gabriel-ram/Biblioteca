import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "/data/notificaciones.db")


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
    
    # 1. Tabla base si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            usuario TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            fecha_creacion TEXT NOT NULL
        )
    ''')
    
    # 2. Migración idempotente de columnas (ALTER TABLE ADD COLUMN)
    cursor.execute("PRAGMA table_info(notificaciones)")
    columnas_existentes = {row['name'] for row in cursor.fetchall()}
    
    nuevas_columnas = [
        ("correo_destino", "TEXT"),
        ("asunto", "TEXT"),
        ("estado", "TEXT"),
        ("intentos", "INTEGER NOT NULL DEFAULT 0"),
        ("proximo_intento", "TEXT"),
        ("ultimo_error", "TEXT"),
        ("fecha_envio", "TEXT"),
        ("clave_idempotencia", "TEXT"),
        ("datos", "TEXT")
    ]
    
    for col_nombre, col_tipo in nuevas_columnas:
        if col_nombre not in columnas_existentes:
            cursor.execute(f"ALTER TABLE notificaciones ADD COLUMN {col_nombre} {col_tipo}")
            
    # 3. Filas existentes pasan a HISTORICA (no se procesan por el worker de correo)
    cursor.execute("UPDATE notificaciones SET estado = 'HISTORICA' WHERE estado IS NULL")
    
    # 4. Índice único sobre clave_idempotencia (permite múltiples NULLs en SQLite)
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notificaciones_clave_idempotencia 
        ON notificaciones(clave_idempotencia)
    ''')
    
    conn.commit()
    conn.close()
