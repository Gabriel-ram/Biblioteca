# CHANGELOG - Refactor Microservicios v2

## [F8] - Avisos Programados y Eventos de Notificación en Préstamos

### Cliente HTTP (`prestamos/clients.py`)
- Ampliado `NotificacionesClient.enviar_notificacion` para soportar el contrato completo de Notificaciones:
  - Parámetros: `tipo`, `usuario`, `correo=None`, `mensaje=None`, `datos=None`, `clave=None`.
  - Envía la carga útil en formato JSON al endpoint `POST /notificar`.
  - Mantiene captura de `RequestException` traduciéndola a `ServicioNoDisponible` con log que no expone datos sensibles.

### Eventos en el Ciclo de Vida de Préstamos (`prestamos/app.py`)
- **`POST /prestamos` (Evento `PRESTAMO`)**:
  - Al crear exitosamente un préstamo, si `NOTIFICAR_PRESTAMO` está activo (por defecto `true`), consulta el correo del usuario asociado.
  - Si el usuario no tiene correo: no envía evento y registra un log informativo sin PII (`Préstamo #id registrado sin notificación: usuario sin correo`).
  - Si el usuario tiene correo: envía evento `PRESTAMO` con clave `PRESTAMO:<id>` y carga `datos: {titulo, fecha_limite}` (fecha en formato legible `YYYY-MM-DD`).
  - Operación best-effort: fallos o timeouts en Notificaciones nunca revierten el préstamo creado ni propagan error al cliente (responde **HTTP 201**).
- **`PUT /prestamos/<id>/devolucion` (Evento `MULTA`)**:
  - Al devolverse un préstamo con retraso, inserta el registro en la tabla `multas` con `notificada = 0`.
  - Si el usuario cuenta con correo, intenta enviar el evento `MULTA` con clave `MULTA:<prestamo_id>` y datos `{titulo, monto, dias_retraso}`.
  - Si Notificaciones responde **HTTP 202**, actualiza atómicamente `multas.notificada = 1`.
  - Tolerancia a caídas: si Notificaciones no está disponible o falla, la devolución responde **HTTP 200** igualmente y la multa se conserva con `notificada = 0` para su posterior reenvío.
- **`POST /prestamos/revisar-vencimientos` (Revisión Batch Idempotente)**:
  - Consulta préstamos en estado `ACTIVO` que no hayan recibido aviso (`aviso_enviado_en IS NULL` y `aviso_vencimiento_enviado = 0`).
  - Si `0 <= dias_restantes <= DIAS_AVISO`:
    - Incrementa el contador de `revisados`.
    - Si el usuario no tiene correo: incrementa `sin_correo` y **no** marca el préstamo.
    - Si tiene correo: envía `POR_VENCER` con clave `POR_VENCER:<id>:<fecha_limite>`.
    - Solo ante **HTTP 202**, actualiza `aviso_enviado_en` y `aviso_vencimiento_enviado = 1`, e incrementa `avisados`.
  - Reintento de multas: para multas con `notificada = 0` cuyos usuarios tengan correo, reintenta el envío con clave `MULTA:<prestamo_id>` y actualiza `notificada = 1` si responde **HTTP 202** (incrementando `multas_reenviadas`).
  - Cortocircuito de seguridad: ante fallo de conexión (`ServicioNoDisponible`), aborta el ciclo inmediatamente y responde con `notificaciones_disponible = false` sin marcar préstamos.
  - Respuesta JSON: `{"revisados": n, "avisados": n, "multas_reenviadas": n, "sin_correo": n, "notificaciones_disponible": true|false}` con código **HTTP 200**.

### Scripts y Automatización
- **`scripts/ejecutar_avisos.sh`**: Script bash para invocación periódica desde Linux/cron. Acepta `BASE_URL` (por defecto `http://127.0.0.1:8002`), credenciales Basic Auth opcionales (`BASIC_AUTH_USER`/`BASIC_AUTH_PASSWORD`), imprime respuesta y finaliza con código de salida `1` ante respuesta no-200.
- **`scripts/ejecutar_avisos.ps1`**: Script PowerShell nativo con idéntica lógica para entornos Windows puros.
- **`docs/AVISOS.md`**: Documentación de la periodicidad recomendada (cron diario a las 08:00 `0 8 * * *`) y guía paso a paso para programar tareas en Linux (`crontab`) y Windows (`Task Scheduler`).

### Verificación y Pruebas
- Creado `scripts/verify_f8.sh` evaluando integralmente:
  - Escenario A: Creación de préstamo con notificación `PRESTAMO` verificada en Mailpit.
  - Escenario B: Revisión de vencimientos (`POR_VENCER`) e idempotencia (segunda corrida da `avisados = 0` sin duplicados).
  - Escenario C: Resiliencia con servicio de Notificaciones detenido (`notificaciones_disponible: false`, préstamo no marcado) y recuperación posterior.
  - Escenario D: Multa por devolución tardía (`notificada = 1`), caso degradado con Notificaciones detenido (`notificada = 0`) y reenvío automático en la siguiente revisión.
  - Escenario E: Usuario sin correo (`sin_correo = 1`, préstamo no marcado).
  - Escenario F: Verificación estricta de ausencia de CI y direcciones completas de correo en logs.
  - Escenario G: Ejecución exitosa de `test_endpoints.sh`, `test_concurrencia.sh` y `ejecutar_avisos.sh`.

---

## [F7] - Envío de Correos en Notificaciones

### Base de Datos (`notificaciones/database.py`)
- Migración idempotente en `init_db()` mediante `ALTER TABLE ADD COLUMN` para la tabla `notificaciones`:
  - Columnas: `correo_destino TEXT`, `asunto TEXT`, `estado TEXT`, `intentos INTEGER NOT NULL DEFAULT 0`, `proximo_intento TEXT`, `ultimo_error TEXT`, `fecha_envio TEXT`, `clave_idempotencia TEXT`, `datos TEXT`.
  - Estados soportados: `PENDIENTE`, `ENVIADA`, `FALLIDA` y `HISTORICA`.
  - Filas preexistentes asignadas automáticamente a `HISTORICA` para evitar envíos no deseados de datos legados.
  - Índice único sobre clave de idempotencia: `CREATE UNIQUE INDEX IF NOT EXISTS idx_notificaciones_clave_idempotencia ON notificaciones(clave_idempotencia)` (permite múltiples registros con `NULL`).

### Worker de Envío Asíncrono (`notificaciones/worker.py`)
- Hilo demonio (`threading.Thread`) iniciado una sola vez por proceso bajo Gunicorn (`--workers 1 --threads 4`).
- Ciclo periódico de sondeo cada `WORKER_INTERVAL` segundos (por defecto 5 s).
- Reclamo atómico de notificaciones pendientes (`estado = 'PENDIENTE'` y `proximo_intento <= ahora`) con bloqueo temporal de 120 s mediante `UPDATE ... WHERE rowcount == 1`.
- Estrategia de reintentos con backoff progresivo (30 s, 2 min, 10 min, 1 h, 1 h) hasta alcanzar `MAX_INTENTOS` (por defecto 5), tras lo cual la notificación pasa a `FALLIDA`.

### Módulo de Correo y Seguridad (`notificaciones/mailer.py`)
- Envío multipart (texto plano y HTML auto-contenido) mediante `smtplib` y `EmailMessage`.
- Soporte para modos `none` (Mailpit sin autenticación), `starttls` (puerto 587) y `ssl` (puerto 465).
- Plantillas diferenciadas para `PRESTAMO`, `POR_VENCER` y `MULTA` con escape HTML de datos de usuario/libro y pie de contacto (`BIBLIOTECA_CONTACTO`).
- Enmascaramiento estricto en logs: nunca se registran contraseñas ni correos completos (se utiliza el identificador y formato `a***@dominio`).

### Cambios de Contrato en la API (`notificaciones/app.py`)
- **`POST /notificar`**:
  - Acepta payload extendido: `{tipo, usuario, correo, mensaje, datos: {titulo, fecha_limite, monto, ...}, clave}`.
  - Validación de `tipo` obligatorio (`PRESTAMO`, `POR_VENCER`, `MULTA`) y formato de correo electrónico (HTTP 400 si son inválidos).
  - Deduplicación por `clave`: responde **HTTP 202** con `{"status": "registrado", "id": ..., "duplicada": true|false}`.
  - **Compatibilidad**: si no se proporciona `correo`, responde **HTTP 202** y almacena la notificación en estado `FALLIDA` con `ultimo_error = 'sin correo destino'`. *(Nota de compatibilidad: mientras Préstamos no envíe el correo en la fase correspondiente, las notificaciones originadas por devoluciones o recordatorios antiguos quedarán en estado FALLIDA sin reintentos).*
- **`GET /notificaciones`**: Soporte para filtros de consulta `?usuario=`, `?estado=`, `?tipo=`, ordenadas por `id DESC`.
- **`POST /notificaciones/<id>/reintentar`**:
  - Responde **HTTP 404** si el ID no existe.
  - Responde **HTTP 409** si el estado actual no es `FALLIDA` o no cuenta con correo destino válido.
  - Si es elegible, responde **HTTP 200** y reencola a `PENDIENTE` con `intentos = 0` y `proximo_intento = ahora`.
- **`GET /health`**: Ahora incluye el campo `"pendientes": n` con la cantidad de notificaciones en cola pendientes de envío.

---

## [F6] - Cliente HTTP de Préstamos y Resiliencia

### Clientes HTTP Centralizados (`prestamos/clients.py`)
- Creadas las clases `CatalogoClient` y `NotificacionesClient` utilizando `requests.Session` para reusar conexiones TCP y pools HTTP.
- Definida la excepción personalizada `ServicioNoDisponible` que captura y traduce cualquier `requests.exceptions.RequestException`.
- Configuración dinámica de timeouts (conexión, lectura) mediante tupla `(connect_timeout, read_timeout)` a través de variables de entorno:
  - `CATALOGO_TIMEOUT`: valor por defecto 3 segundos.
  - `NOTIFICACIONES_TIMEOUT`: valor por defecto 2 segundos.
  - Añadidas a `.env.example` y `.env`.
- Eliminada la constante fija `REQUEST_TIMEOUT` y las llamadas dispersas de `requests.*` en `prestamos/app.py`.

### Comportamiento de Resiliencia y Contratos (`prestamos/app.py`)
- **Creación de Préstamo (`POST /prestamos`)**:
  - Si Catálogo no responde o supera el timeout, responde **HTTP 503** con formato estándar `{"error": "No se pudo establecer comunicación con el servicio de Catálogo"}` y no almacena ningún préstamo localmente.
  - Si Catálogo descontó el ejemplar pero la inserción local en SQLite falla, ejecuta rollback compensatorio llamando a `reponer_disponibilidad(libro_id)`.
  - Si la compensación también falla o Catálogo no responde, emite un log a nivel `CRITICAL` con los identificadores técnicos (`libro_id`, `prestamo_id=None`) sin filtrar información personal (sin CI, nombres ni correos).
- **Devolución de Préstamo (`PUT /prestamos/<id>/devolucion`)**:
  - Primero invoca a Catálogo mediante `reponer_disponibilidad(libro_id)`. Si Catálogo no responde o hay timeout, responde **HTTP 503** con `{"error": "Catálogo no está disponible; el préstamo continúa activo"}` y el préstamo permanece en estado `ACTIVO`.
  - Si Catálogo responde **HTTP 409** (ejemplares ya al máximo por la semántica atómica de F3), registra un `warning` y procede a cerrar la devolución localmente.
  - Si la reposición en Catálogo tiene éxito pero la escritura en SQLite falla, ejecuta compensación llamando a `descontar_disponibilidad(libro_id)` y registra el fallo en logs.
- **Notificaciones (Multas y Avisos)**:
  - Las llamadas a Notificaciones operan bajo el patrón best-effort: un fallo en Notificaciones nunca aborta una operación exitosa ni propaga errores **HTTP 500** al cliente.
  - En caso de indisponibilidad o rechazo por parte del servicio de Notificaciones, registra un log a nivel `WARNING` que no contiene datos sensibles (`ci` ni correos electrónicos).
- **Proxy de Catálogo (`/libros`, `/autores`)**:
  - Mantenidos plenamente operativos utilizando `CatalogoClient`, devolviendo **HTTP 503** ante fallos de conexión o timeouts de Catálogo.

---

## [F5] - Usuarios dentro de Préstamos

### Base de Datos (`prestamos/database.py`)
- Migración idempotente en `init_db()` mediante `ALTER TABLE ADD COLUMN`:
  - Tabla `usuarios`: columnas `codigo TEXT`, `correo TEXT NOT NULL DEFAULT ''`, `tipo TEXT NOT NULL DEFAULT 'ESTUDIANTE'`, `activo INTEGER NOT NULL DEFAULT 1`.
  - Migración de datos existentes: rellena `codigo = ci` para usuarios existentes, asigna `tipo = 'ESTUDIANTE'`, `correo = ''`, `activo = 1`.
  - Creación de índice único: `CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_codigo ON usuarios(codigo)`.
  - Tabla `prestamos`: columnas `usuario_id INTEGER`, `libro_titulo TEXT`, `aviso_enviado_en TEXT`. Enlace automático de `usuario_id` para préstamos existentes.
  - Tabla `multas`: columna `notificada INTEGER NOT NULL DEFAULT 0`.
  - Conservadas columnas heredadas `ci` y `aviso_vencimiento_enviado` sin pérdida de datos.

### Módulo y Blueprint de Usuarios (`prestamos/usuarios.py`)
- Rutas separadas de la lógica de servicio:
  - `POST /usuarios {codigo, nombre, correo, tipo}`:
    - **201 Created** al registrar.
    - **400 Bad Request** si falta algún campo, el correo no tiene formato válido (`regex`) o el tipo no es `ESTUDIANTE` ni `DOCENTE`.
    - **409 Conflict** si el código ya existe.
    - Mantiene retrocompatibilidad con formato antiguo `{nombre, ci}`.
  - `GET /usuarios`: soporta filtros `?tipo=` y `?q=` (búsqueda sobre nombre o código).
  - `GET /usuarios/<id>`: **200 OK** con datos del usuario, **404 Not Found** si no existe.
  - `PUT /usuarios/<id>`: **200 OK** con usuario actualizado; valida unicidad de código (409), formato de correo y tipo (400) y existencia (404).
  - `DELETE /usuarios/<id>`: baja lógica (`activo = 0`), **204 No Content**; **409 Conflict** si tiene préstamos en estado `ACTIVO`; **404 Not Found** si no existe.

### Contratos de Préstamos (`prestamos/app.py`)
- `POST /prestamos`:
  - Formato nuevo: `{libro_id, usuario_id}` o `{libro_id, codigo_usuario}`. Valida existencia (404) y estado activo (409 si `activo == 0`).
  - Formato antiguo: `{libro_id, usuario, ci}`. Busca usuario por `codigo = ci`; si no existe, lo crea con correo vacío.
  - Almacenamiento: guarda `usuario_id`, `libro_titulo` (tomado de la respuesta de Catálogo) y copia de `usuario` (nombre).
  - Respuesta: conserva todos los campos anteriores y añade `usuario_id` y `libro_titulo`.
- `GET /prestamos`: añade soporte para filtros `?usuario_id=` y `?estado=` además de `?usuario=`.

### Seguridad de Datos
- Las columnas `ci` y correos electrónicos no son emitidas en logs del servicio.

---

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
