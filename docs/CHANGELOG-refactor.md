# CHANGELOG - Refactor Microservicios v2

## [F4] - Integridad del catálogo

### Contrato de DELETE `/libros/<id>`
- Responde **HTTP 404** si el libro no existe.
- Responde **HTTP 409** si `ejemplares_disponibles < ejemplares_totales` (existen ejemplares prestados).
- Si todos los ejemplares están disponibles, elimina el libro y responde **HTTP 204** sin contenido.

### Contrato de PUT `/libros/<id>`
- Validación de `ejemplares_totales`:
  - Si el valor no es un entero o es menor que 1, responde **HTTP 400**.
  - Si cambia `ejemplares_totales`, se calcula `prestados = total_anterior - disponibles_anterior`:
    - Si `nuevo_total < prestados`, responde **HTTP 409** (no se puede reducir por debajo de los ejemplares prestados).
    - Si es válido, actualiza `ejemplares_disponibles = nuevo_total - prestados` y el estado a `DISPONIBLE` (si `disponibles > 0`) o `AGOTADO` (si `disponibles == 0`), respondiendo **HTTP 200**.

---

## [F3] - SQLite con WAL y operaciones atómicas

### Cambios en Catálogo
- `PATCH /libros/<id>/disponibilidad` (`reponer`): ahora responde **HTTP 409** si ya están todos los ejemplares disponibles (`ejemplares_disponibles == ejemplares_totales`). Si el libro no existe, responde **HTTP 404**.
- `PATCH /libros/<id>/disponibilidad` (`descontar`): operación atómica en una sola sentencia `UPDATE ... WHERE id = ? AND ejemplares_disponibles > 0`. Responde **HTTP 409** si no hay ejemplares disponibles y **HTTP 404** si el libro no existe.
- Eliminado el patrón de `SELECT` previo seguido de `UPDATE` en cambios de disponibilidad.

### Conexión SQLite y PRAGMAs
- Configurados en `catalogo/database.py`, `prestamos/database.py` y `notificaciones/database.py`:
  - `sqlite3.connect(DB_PATH, timeout=10)`
  - `PRAGMA journal_mode=WAL;`
  - `PRAGMA busy_timeout=5000;`
  - `PRAGMA foreign_keys=ON;`
  - `PRAGMA synchronous=NORMAL;`
  - `row_factory = sqlite3.Row`
- `init_db()` se mantiene idempotente y preserva los datos de volúmenes existentes.

### Resiliencia en Préstamos
- `prestamos/app.py`: Si Catálogo responde **409** a la operación `reponer` (en devolución de préstamo o rollback compensatorio), Préstamos registra un `warning` y continúa el flujo con normalidad, sin devolver error 500 ni 502.

### Pruebas de Concurrencia
- Creado `scripts/test_concurrencia.sh` para verificar atomicidad bajo 20 peticiones paralelas de descuento (3 respuestas 200, 17 respuestas 409, 0 errores 500, stock final = 0, y verificación de logs).
