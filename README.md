# Sistema de Gestión de Biblioteca (Microservicios)

Este proyecto implementa una arquitectura basada en **microservicios independientes** para la administración de una biblioteca digital. Cada microservicio cuenta con su propia base de datos SQLite aislada, comunicación síncrona mediante REST/HTTP (JSON), despliegue en contenedores Docker y orquestación unificada mediante Docker Compose.

---

## 📐 Arquitectura del Sistema

```text
                                  +-----------------------+
                                  |    Docker Compose     |
                                  +-----------------------+
                                              |
                     +------------------------+------------------------+
                     |                        |                        |
             +---------------+        +---------------+        +---------------+
             |   Catálogo    |        |   Préstamos   |        | Notificaciones|
             |   (Python)    |        |   (Python)    |        |   (Python)    |
             | Puerto: 8001  |        | Puerto: 8002  |        | Puerto: 8003  |
             +-------+-------+        +-------+-------+        +-------+-------+
                     |                        |                        |
              catalogo_data            prestamos_data          notificaciones_data
              (catalogo.db)            (prestamos.db)          (notificaciones.db)
```

### Principales Principios Arquitectónicos
- **Base de Datos por Servicio (Database per Service):** Cada servicio gestiona su persistencia de forma independiente mediante volúmenes nombrados de Docker montados en `/data`.
- **Desacoplamiento y Resiliencia:** El microservicio de Préstamos realiza llamadas HTTP a Catálogo (gestión de stock) y Notificaciones (alertas). Si el servicio de Notificaciones falla, el flujo de devolución no se bloquea (tolerancia a fallos con timeout de 3 segundos).
- **Devoluciones consistentes:** Préstamos solo cambia el estado local a `DEVUELTO` después de que Catálogo confirme la reposición. Si Catálogo no responde o rechaza la operación, el préstamo permanece `ACTIVO`.
- **Avisos idempotentes:** Cada préstamo registra si su aviso de próximo vencimiento fue aceptado por Notificaciones. Los avisos fallidos quedan pendientes para una revisión posterior.
- **Multas con tolerancia a fallos:** La devolución se guarda aunque Notificaciones no responda; el envío del aviso de multa es best-effort y no tiene reintento automático.
- **Rollback Transaccional Distribuido:** Si la persistencia local de un préstamo falla tras haber reservado stock en Catálogo, el servicio realiza una llamada de compensación (`PATCH /libros/<id>/disponibilidad` con `{"operacion": "reponer"}`).

---

## 📂 Estructura del Repositorio

```text
.
├── docker-compose.yml
├── README.md
├── .gitignore
├── catalogo/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   └── database.py
├── prestamos/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── database.py
│   └── templates/
│       └── index.html
└── notificaciones/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py
    └── database.py
```

---

## 🚀 Despliegue con Docker Compose

### Requisitos Previos
- [Docker](https://www.docker.com/) instalado.
- [Docker Compose](https://docs.docker.com/compose/) instalado.

### Comandos de Ejecución

1. **Iniciar todos los microservicios:**
   ```bash
   docker-compose up --build
   ```

2. **Ejecutar en modo desacoplado (Background):**
   ```bash
   docker-compose up -d --build
   ```

3. **Verificar estado de los contenedores:**
   ```bash
   docker-compose ps
   ```

4. **Ver logs del sistema:**
   ```bash
   docker-compose logs -f
   ```

5. **Detener y remover contenedores:**
   ```bash
   docker-compose down
   ```

---

## ⚙️ Configuración y Variables de Entorno

El servicio de **Préstamos** utiliza las siguientes variables de entorno (configuradas en `docker-compose.yml`):

| Variable | Valor por Defecto | Descripción |
| :--- | :--- | :--- |
| `CATALOGO_URL` | `http://catalogo:8001` | URL interna de red Docker para el servicio de Catálogo |
| `NOTIFICACIONES_URL` | `http://notificaciones:8003` | URL interna de red Docker para Notificaciones |
| `DIAS_PRESTAMO` | `7` | Días permitidos por préstamo antes de generar mora |
| `MULTA_POR_DIA` | `5` | Monto acumulado por día de retraso |
| `DIAS_AVISO` | `2` | Ventana de días para alertar préstamos próximos a vencer |

---

## 📖 Especificación de Endpoints y Guía de Uso (cURL)

### 1. Servicio de Catálogo (`http://localhost:8001`)

- **GET `/health`**
  - Estado del servicio.
  ```bash
  curl -X GET http://localhost:8001/health
  ```

- **POST `/autores`**
  - Registrar autor.
  ```bash
  curl -X POST http://localhost:8001/autores \
    -H "Content-Type: application/json" \
    -d '{"nombre": "Gabriel García Márquez", "nacionalidad": "Colombiana"}'
  ```

- **GET `/autores`**
  - Listar autores.
  ```bash
  curl -X GET http://localhost:8001/autores
  ```

- **POST `/libros`**
  - Registrar un nuevo libro en el catálogo.
  ```bash
  curl -X POST http://localhost:8001/libros \
    -H "Content-Type: application/json" \
    -d '{"titulo": "Cien Años de Soledad", "autor_id": 1, "ejemplares_totales": 3}'
  ```

- **GET `/libros`**
  - Obtener lista de libros (Soporta filtro `?disponible=true`).
  ```bash
  # Obtener todos los libros
  curl -X GET http://localhost:8001/libros

  # Filtrar solo libros disponibles
  curl -X GET "http://localhost:8001/libros?disponible=true"
  ```

- **GET `/libros/<id>`**
  - Obtener un libro por su ID.
  ```bash
  curl -X GET http://localhost:8001/libros/1
  ```

- **PUT `/libros/<id>`**
  - Actualizar datos de un libro.
  ```bash
  curl -X PUT http://localhost:8001/libros/1 \
    -H "Content-Type: application/json" \
    -d '{"titulo": "Cien Años de Soledad - Edición Especial", "autor_id": 1, "ejemplares_totales": 5, "ejemplares_disponibles": 5}'
  ```

- **DELETE `/libros/<id>`**
  - Eliminar un libro.
  ```bash
  curl -X DELETE http://localhost:8001/libros/1
  ```

- **PATCH `/libros/<id>/disponibilidad`**
  - Modificar el stock del libro (`descontar` o `reponer`).
  ```bash
  curl -X PATCH http://localhost:8001/libros/1/disponibilidad \
    -H "Content-Type: application/json" \
    -d '{"operacion": "descontar"}'
  ```

---

### 2. Servicio de Préstamos (`http://localhost:8002`)

- **GET `/health`**
  - Estado del servicio.
  ```bash
  curl -X GET http://localhost:8002/health
  ```

- **POST `/prestamos`**
  - Registrar un nuevo préstamo (descuenta automáticamente del catálogo). Requiere `usuario`, `ci` (de 1 a 8 dígitos) y `libro_id` (o alternativamente `usuario_id` y `libro_id`). Permite opcionalmente especificar `dias_prestamo` (entero positivo con los días de duración del préstamo; por defecto toma `DIAS_PRESTAMO` = 7).
  ```bash
  curl -X POST http://localhost:8002/prestamos \
    -H "Content-Type: application/json" \
    -d '{"usuario": "juan.perez", "ci": "12345678", "libro_id": 1, "dias_prestamo": 14}'
  ```

El catálogo de demostración contiene actualmente *La casa de los espíritus* y diez títulos añadidos: *Don Quijote de la Mancha*, *La Odisea*, *Orgullo y prejuicio*, *Frankenstein*, *Crimen y castigo*, *Cien años de soledad*, *El principito*, *1984*, *Rayuela* y *Ficciones*. Estos registros están guardados en el volumen Docker `catalogo_data`; se conservan al reiniciar contenedores, pero se eliminan si ejecutas `docker compose down -v`.

- **GET `/prestamos`**
  - Listar préstamos (filtro opcional `?usuario=juan.perez`).
  ```bash
  curl -X GET "http://localhost:8002/prestamos?usuario=juan.perez"
  ```

- **PUT `/prestamos/<id>/devolucion`**
  - Registrar devolución de un libro. Solo se confirma localmente si Catálogo confirma la reposición; calcula multas y notifica si aplica.
  ```bash
  curl -X PUT http://localhost:8002/prestamos/1/devolucion
  ```

- **POST `/prestamos/revisar-vencimientos`**
  - Proceso batch que busca préstamos por vencer. Cada aviso aceptado se marca para no repetirlo en revisiones posteriores; si Notificaciones falla, se puede reintentar.
  ```bash
  curl -X POST http://localhost:8002/prestamos/revisar-vencimientos
  ```

---

### 3. Servicio de Notificaciones (`http://localhost:8003`)

- **GET `/health`**
  - Estado del servicio.
  ```bash
  curl -X GET http://localhost:8003/health
  ```

- **POST `/notificar`**
  - Recibe un evento de notificación, lo imprime en consola y lo guarda en la BD.
  ```bash
  curl -X POST http://localhost:8003/notificar \
    -H "Content-Type: application/json" \
    -d '{"tipo": "MULTA", "usuario": "juan.perez", "mensaje": "Tienes una multa pendiente de $10.00"}'
  ```

- **GET `/notificaciones`**
  - Historial de notificaciones registradas.
  ```bash
  curl -X GET http://localhost:8003/notificaciones
  ```

---

## 🧪 Pruebas Rápidas de Verificación (Flujo Completo)

1. **Crear autor y libro:**
   ```bash
   curl -X POST http://localhost:8001/autores -H "Content-Type: application/json" -d '{"nombre": "Isabel Allende", "nacionalidad": "Chilena"}'
   curl -X POST http://localhost:8001/libros -H "Content-Type: application/json" -d '{"titulo": "La Casa de los Espíritus", "autor_id": 1, "ejemplares_totales": 1}'
   ```

2. **Solicitar un préstamo:**
   ```bash
   curl -X POST http://localhost:8002/prestamos -H "Content-Type: application/json" -d '{"usuario": "maria.gomez", "libro_id": 1}'
   ```

3. **Verificar que el catálogo marca el libro como AGOTADO:**
   ```bash
   curl -X GET http://localhost:8001/libros/1
   ```

4. **Intentar pedir el mismo libro sin stock (retornará HTTP 409):**
   ```bash
   curl -X POST http://localhost:8002/prestamos -H "Content-Type: application/json" -d '{"usuario": "carlos.lopez", "libro_id": 1}'
   ```

5. **Devolver el libro (repone stock en Catálogo):**
   ```bash
   curl -X PUT http://localhost:8002/prestamos/1/devolucion
   ```

6. **Consultar el historial de notificaciones:**
   ```bash
   curl -X GET http://localhost:8003/notificaciones
   ```

---

## 🖥️ Interfaz web de demostración

Con los contenedores iniciados, abre **http://localhost:8002/** en el navegador. La página permite consultar libros y disponibilidad, registrar préstamos, registrar devoluciones, consultar el historial de notificaciones y ejecutar manualmente una revisión de vencimientos. La interfaz usa CSS local y no necesita descargar recursos externos.

### Demostrar tolerancia a fallos

Detén temporalmente Notificaciones desde otra terminal:

```bash
docker stop notificaciones_service
```

Actualiza la interfaz. El historial indicará que Notificaciones no está disponible, pero podrás continuar registrando préstamos y devoluciones. Los avisos de vencimiento que no se entreguen quedan pendientes y pueden reintentarse al volver a ejecutar la revisión cuando el servicio esté arriba. El aviso de multa es best-effort y no tiene reintento automático.

Restaura el servicio:

```bash
docker start notificaciones_service
```

En cambio, si Catálogo no confirma la reposición, una devolución se rechaza y el préstamo permanece activo. Para volver a revisar avisos pendientes desde la UI, pulsa **Revisar vencimientos**.

### Prueba rápida de la interfaz

1. Arranca el sistema con `docker-compose up -d --build` y abre **http://localhost:8002/**.
2. Indica un usuario, selecciona un libro disponible y pulsa **Crear préstamo**.
3. Comprueba el préstamo activo y pulsa **Devolver** para registrar la devolución.
4. Pulsa **Revisar vencimientos** para ejecutar el proceso batch. Se notifican los préstamos dentro de la ventana `DIAS_AVISO` (incluidos los vencidos); cada aviso aceptado se envía una sola vez por préstamo.
5. Repite la prueba con el contenedor de Notificaciones detenido y comprueba que las operaciones del préstamo siguen respondiendo.

El formulario de préstamo solicita nombre y CI; el CI admite únicamente números, hasta 8 dígitos. Los registros de préstamo que ya existían antes de esta actualización conservan el CI vacío y se muestran con `—`.

---

# ESCENARIO DE PRUEBA

Los comandos de esta sección se ejecutan en **PowerShell**, desde la carpeta del proyecto:

```powershell
Set-Location "C:\Users\GABRIEL\Desktop\Biblioteca"
```

## Detener y volver a iniciar todos los servicios sin borrar datos

Para detener los contenedores de los tres microservicios y mantener los datos, usa:

```powershell
docker compose stop
```

Este comando solo detiene los contenedores. No borra los volúmenes con los libros, autores, préstamos ni notificaciones. Comprueba el estado con:

```powershell
docker compose ps -a
```

Para iniciarlos rápidamente otra vez, sin reconstruir las imágenes:

```powershell
docker compose start
```

Espera unos segundos y verifica que estén activos:

```powershell
docker compose ps
```

Si en lugar de detenerlos quieres eliminar los contenedores y la red, pero conservar los datos, también puedes ejecutar `docker compose down` y después `docker compose up -d`. **No uses `docker compose down -v`** si quieres conservar la información: la opción `-v` elimina los volúmenes.

## Escenario 1: Notificaciones se detiene

Este escenario demuestra que el proceso de préstamo y devolución no depende de que Notificaciones esté en línea. Deja Catálogo y Préstamos funcionando.

1. Detén solo Notificaciones:

  ```powershell
  docker compose stop notificaciones
  docker compose ps
  ```

2. Abre o actualiza **http://localhost:8002/**. En la sección **Notificaciones** debería indicarse que el servicio no está disponible. La consulta de la interfaz sigue pudiendo cargar el catálogo y los préstamos.

3. En **Libros**, escoge un libro disponible. En **Préstamos**, registra uno indicando nombre y CI de hasta ocho dígitos. Luego confirma la devolución con el botón **Devolver**. Ambas operaciones deberían funcionar mientras Catálogo responda.

4. Comprueba que Préstamos sigue activo:

  ```powershell
  Invoke-RestMethod http://localhost:8002/health
  Invoke-RestMethod http://localhost:8002/prestamos
  ```

5. Inicia de nuevo Notificaciones y comprueba su estado:

  ```powershell
  docker compose start notificaciones
  docker compose ps
  Invoke-RestMethod http://localhost:8003/health
  ```

6. Actualiza la página o entra en **Notificaciones**. El historial que ya estaba guardado debe seguir ahí. Para los avisos **POR_VENCER** que no pudieron entregarse, pulsa **Revisar vencimientos** cuando Notificaciones ya esté activa; los avisos aceptados se guardarán en el historial y no se repetirán en próximas revisiones.

  **Importante:** el servicio no puede guardar un aviso que nunca recibió durante la caída. Los avisos de vencimiento pendientes sí se pueden reintentar; el aviso de multa es best-effort y no tiene reintento automático. Al volver a iniciar Notificaciones, se conserva su historial previo, pero eso no recupera automáticamente las notificaciones que se perdieron mientras estaba detenida.

## Escenario 2: Catálogo se detiene

Catálogo administra la disponibilidad del inventario. Sin su confirmación, Préstamos no debe crear ni confirmar movimientos que podrían desajustar el stock.

1. Antes de detener Catálogo, anota un préstamo activo si tienes uno. Si no, crea uno desde la interfaz mientras los tres servicios funcionan.

2. Detén Catálogo:

  ```powershell
  docker compose stop catalogo
  docker compose ps
  ```

3. Desde la interfaz, intenta crear otro préstamo o devolver el activo. La operación debe fallar de forma controlada porque Préstamos no puede comunicarse con Catálogo ni verificar el inventario. Una devolución fallida debe dejar el préstamo como `ACTIVO`.

4. Comprueba por separado que las otras bases y APIs siguen disponibles. El listado local de préstamos no requiere Catálogo:

  ```powershell
  Invoke-RestMethod http://localhost:8002/prestamos
  ```

  Notificaciones es otro servicio independiente. Su salud e historial pueden consultarse directamente, aunque Catálogo esté detenido:

  ```powershell
  Invoke-RestMethod http://localhost:8003/health
  Invoke-RestMethod http://localhost:8003/notificaciones
  ```

  La ruta agregada de la interfaz necesita consultar Catálogo; por eso puede mostrar un error de carga durante esta prueba. Para verificar específicamente que el historial sigue disponible, usa el endpoint directo `http://localhost:8003/notificaciones`.

5. Restaura Catálogo y confirma que responde:

  ```powershell
  docker compose start catalogo
  docker compose ps
  Invoke-RestMethod http://localhost:8001/health
  ```

6. Actualiza la interfaz. Vuelve a probar el préstamo o la devolución; ahora que Catálogo confirmó el inventario, el flujo puede continuar.

## Fin de la demostración

Para detener todos los servicios y conservar datos, utiliza `docker compose stop`. Para volver a ponerlos en marcha después, utiliza `docker compose start`. La información se mantiene en los volúmenes nombrados de Docker mientras estos no se eliminen.
