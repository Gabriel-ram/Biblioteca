# Guía de Avisos Programados de Vencimiento y Reenvío de Multas

Este documento describe el mecanismo de revisión periódica de préstamos próximos a vencer y reintento de multas pendientes en el microservicio de **Préstamos**, así como las instrucciones de automatización para Linux y Windows.

---

## 1. Funcionamiento del Endpoint

El endpoint `POST /prestamos/revisar-vencimientos` realiza una revisión batch idempotente:

1. **Préstamos por vencer**:
   - Identifica préstamos en estado `ACTIVO` cuya fecha límite se encuentre entre la fecha actual y `hoy + DIAS_AVISO` días (`0 <= dias_restantes <= DIAS_AVISO`), que no hayan sido alertados previamente (`aviso_enviado_en IS NULL` y `aviso_vencimiento_enviado = 0`).
   - Si el usuario cuenta con correo electrónico registrado: envía una notificación de tipo `POR_VENCER` a través de `NotificacionesClient` con la clave de deduplicación `POR_VENCER:<prestamo_id>:<fecha_limite>`.
   - Si el servicio de Notificaciones responde **HTTP 202**, actualiza atómicamente `aviso_enviado_en` con la marca de tiempo actual y `aviso_vencimiento_enviado = 1`.
   - Si el usuario **no** tiene correo registrado: incrementa el contador `sin_correo` y **no** marca el préstamo, permitiendo que sea notificado en revisiones futuras si el usuario registra su dirección.

2. **Reintento de multas pendientes**:
   - Localiza multas en estado `notificada = 0` cuyos usuarios posean correo registrado.
   - Envía el evento `MULTA` con clave `MULTA:<prestamo_id>`.
   - Si Notificaciones responde **HTTP 202**, actualiza `notificada = 1`.

3. **Tolerancia a fallos y cortocircuito**:
   - Si la comunicación con Notificaciones falla (`ServicioNoDisponible`), la revisión se aborta de inmediato para no saturar la red ni emitir llamadas infructuosas.
   - Los préstamos no notificados conservan sus marcas en blanco para el siguiente ciclo.

### Formato de Respuesta HTTP 200

```json
{
  "revisados": 2,
  "avisados": 2,
  "multas_reenviadas": 0,
  "sin_correo": 0,
  "notificaciones_disponible": true
}
```

- `revisados`: Total de préstamos en ventana de vencimiento evaluados.
- `avisados`: Total de recordatorios emitidos y aceptados (HTTP 202) en esta corrida.
- `multas_reenviadas`: Total de multas no notificadas previas que lograron enviarse.
- `sin_correo`: Préstamos en ventana de vencimiento cuyos usuarios no tenían correo configurado.
- `notificaciones_disponible`: `true` si el servicio de notificaciones estuvo operativo; `false` si se abortó por caída del servicio.

---

## 2. Periodicidad Recomendada

Se recomienda ejecutar la revisión **una vez al día**, preferiblemente a primera hora de la mañana (ej. **08:00 AM hora local**).

**Expresión Cron estándar**:
```cron
0 8 * * *
```

---

## 3. Programación en Linux (`crontab` / `systemd`)

### Usando `crontab`

1. Abrir la configuración de crontab para el usuario deseado:
   ```bash
   crontab -e
   ```

2. Añadir la siguiente línea (ajustando la ruta absoluta del repositorio y el log):
   ```cron
   0 8 * * * /bin/bash /opt/Biblioteca/scripts/ejecutar_avisos.sh >> /var/log/biblioteca_avisos.log 2>&1
   ```

3. Variables de entorno configurables en el script:
   - `BASE_URL`: URL del servicio de préstamos o gateway (por defecto: `http://127.0.0.1:8002`).
   - `BASIC_AUTH_USER` y `BASIC_AUTH_PASSWORD`: Credenciales opcionales si se invoca a través del Gateway con autenticación básica.

   Ejemplo con variables en crontab:
   ```cron
   0 8 * * * BASE_URL=http://localhost:8080 BASIC_AUTH_USER=admin BASIC_AUTH_PASSWORD=secreto /bin/bash /opt/Biblioteca/scripts/ejecutar_avisos.sh >> /var/log/biblioteca_avisos.log 2>&1
   ```

---

## 4. Programación en Windows (Programador de Tareas / Task Scheduler)

En entornos Windows, se utiliza el script PowerShell `scripts/ejecutar_avisos.ps1`.

### Opción A: Mediante la interfaz gráfica (GUI)

1. Abrir el **Programador de tareas** (`taskschd.msc`).
2. En el panel derecho, hacer clic en **Crear tarea básica...**.
3. **Nombre**: `Biblioteca - Revision de Vencimientos`.
4. **Desencadenador**: Seleccionar **Diariamente** y definir la hora (ej: `08:00:00`).
5. **Acción**: Seleccionar **Iniciar un programa**.
6. **Configuración de programa**:
   - **Programa o script**: `powershell.exe`
   - **Agregar argumentos**:
     ```text
     -ExecutionPolicy Bypass -File "C:\ruta\al\proyecto\Biblioteca\scripts\ejecutar_avisos.ps1"
     ```
   - **Iniciar en**: `C:\ruta\al\proyecto\Biblioteca`
7. Finalizar el asistente guardando la tarea.

### Opción B: Mediante PowerShell (Línea de comandos como Administrador)

Ejecutar en una consola con privilegios de Administrador:

```powershell
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument '-ExecutionPolicy Bypass -File "C:\ruta\al\proyecto\Biblioteca\scripts\ejecutar_avisos.ps1"' `
    -WorkingDirectory "C:\ruta\al\proyecto\Biblioteca"

$Trigger = New-ScheduledTaskTrigger -Daily -At "08:00AM"

Register-ScheduledTask -TaskName "Biblioteca_Avisos_Vencimiento" `
    -Action $Action `
    -Trigger $Trigger `
    -Description "Revisión diaria de préstamos próximos a vencer y reenvío de multas" `
    -User "NT AUTHORITY\SYSTEM"
```

