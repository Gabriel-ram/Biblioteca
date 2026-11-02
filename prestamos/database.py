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

    # Migrar columnas en prestamos
    cursor.execute("PRAGMA table_info(prestamos)")
    cols_prestamos = {row[1] for row in cursor.fetchall()}
    if 'aviso_vencimiento_enviado' not in cols_prestamos:
        cursor.execute(
            "ALTER TABLE prestamos ADD COLUMN aviso_vencimiento_enviado "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if 'ci' not in cols_prestamos:
        cursor.execute("ALTER TABLE prestamos ADD COLUMN ci TEXT")
    if 'usuario_id' not in cols_prestamos:
        cursor.execute("ALTER TABLE prestamos ADD COLUMN usuario_id INTEGER")
    if 'libro_titulo' not in cols_prestamos:
        cursor.execute("ALTER TABLE prestamos ADD COLUMN libro_titulo TEXT")
    if 'aviso_enviado_en' not in cols_prestamos:
        cursor.execute("ALTER TABLE prestamos ADD COLUMN aviso_enviado_en TEXT")
    
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

    cursor.execute("PRAGMA table_info(multas)")
    cols_multas = {row[1] for row in cursor.fetchall()}
    if 'notificada' not in cols_multas:
        cursor.execute("ALTER TABLE multas ADD COLUMN notificada INTEGER NOT NULL DEFAULT 0")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ci TEXT,
            fecha_registro TEXT NOT NULL
        )
    ''')

    cursor.execute("PRAGMA table_info(usuarios)")
    cols_usuarios = {row[1] for row in cursor.fetchall()}
    if 'codigo' not in cols_usuarios:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN codigo TEXT")
    if 'correo' not in cols_usuarios:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN correo TEXT NOT NULL DEFAULT ''")
    if 'tipo' not in cols_usuarios:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN tipo TEXT NOT NULL DEFAULT 'ESTUDIANTE'")
    if 'activo' not in cols_usuarios:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN activo INTEGER NOT NULL DEFAULT 1")

    # Poblar con usuarios que ya tengan préstamos registrados
    cursor.execute("""
        INSERT OR IGNORE INTO usuarios (nombre, ci, codigo, fecha_registro, tipo, activo, correo)
        SELECT DISTINCT usuario, ci, ci, MIN(fecha_prestamo), 'ESTUDIANTE', 1, ''
        FROM prestamos
        WHERE usuario IS NOT NULL AND ci IS NOT NULL AND TRIM(ci) != ''
        GROUP BY ci
    """)

    # Rellenar codigo = ci en usuarios existentes donde falte codigo
    cursor.execute("""
        UPDATE usuarios 
        SET codigo = ci 
        WHERE (codigo IS NULL OR TRIM(codigo) = '') AND ci IS NOT NULL AND TRIM(ci) != ''
    """)

    # Asegurar valores por defecto en columnas de usuarios existentes
    cursor.execute("UPDATE usuarios SET correo = '' WHERE correo IS NULL")
    cursor.execute("UPDATE usuarios SET tipo = 'ESTUDIANTE' WHERE tipo IS NULL OR TRIM(tipo) = ''")
    cursor.execute("UPDATE usuarios SET activo = 1 WHERE activo IS NULL")

    # Índice único sobre usuarios.codigo
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_codigo ON usuarios(codigo)")

    # Enlazar usuario_id en prestamos existentes si no lo tienen
    cursor.execute("""
        UPDATE prestamos
        SET usuario_id = (
            SELECT id FROM usuarios 
            WHERE (usuarios.codigo = prestamos.ci OR usuarios.ci = prestamos.ci)
            LIMIT 1
        )
        WHERE usuario_id IS NULL AND ci IS NOT NULL AND TRIM(ci) != ''
    """)
    
    conn.commit()
    conn.close()
