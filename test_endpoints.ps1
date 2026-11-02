# ==============================================================================
# SCRIPT POWERSHELL DE PRUEBAS AUTOMATIZADAS - SISTEMA DE BIBLIOTECA
# ==============================================================================

$BaseCatalogo = "http://localhost:8001"
$BasePrestamos = "http://localhost:8002"
$BaseNotificaciones = "http://localhost:8003"

function Print-Title {
    param([string]$title)
    Write-Host "`n====================================================================" -ForegroundColor Cyan
    Write-Host $title -ForegroundColor Cyan
    Write-Host "====================================================================" -ForegroundColor Cyan
}

function Print-Step {
    param([string]$step)
    Write-Host "`n>>> $step" -ForegroundColor Yellow
}

function Verify-Code {
    param([int]$expected, [int]$actual, [string]$desc)
    if ($expected -eq $actual) {
        Write-Host "[OK] $desc (HTTP $actual)" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] $desc (Esperado: $expected, Obtenido: $actual)" -ForegroundColor Red
    }
}

# 1. Healthchecks
Print-Title "1. VERIFICACION DE HEALTHCHECKS (/health)"

$services = @(
    @{ Name = "catalogo"; Url = "$BaseCatalogo/health" },
    @{ Name = "prestamos"; Url = "$BasePrestamos/health" },
    @{ Name = "notificaciones"; Url = "$BaseNotificaciones/health" }
)

foreach ($s in $services) {
    Write-Host "Esperando a $($s.Name)... " -NoNewline
    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        try {
            $resp = Invoke-RestMethod -Uri $s.Url -Method Get -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($resp.status -eq "UP") {
                Write-Host "Listo (UP)" -ForegroundColor Green
                $ready = $true
                break
            }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        Write-Host "No respondio a tiempo" -ForegroundColor Red
    }
}

# 2. Catalogo: Autor y Libro
Print-Title "2. GESTION EN CATALOGO: AUTOR Y LIBRO"

Print-Step "Creando Autor (POST /autores)"
$autorBody = @{ nombre = "Gabriel Garcia Marquez"; nacionalidad = "Colombiana" } | ConvertTo-Json
$autorResp = Invoke-RestMethod -Uri "$BaseCatalogo/autores" -Method Post -ContentType "application/json" -Body $autorBody
Write-Host "Autor creado: $($autorResp | ConvertTo-Json -Compress)"
$autorId = $autorResp.id

Print-Step "Creando Libro con 1 ejemplar (POST /libros)"
$timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$libroBody = @{
    titulo = "Cien Anos de Soledad ($timestamp)"
    autor_id = $autorId
    ejemplares_totales = 1
} | ConvertTo-Json

$libroResp = Invoke-RestMethod -Uri "$BaseCatalogo/libros" -Method Post -ContentType "application/json" -Body $libroBody
Write-Host "Libro creado: $($libroResp | ConvertTo-Json -Compress)"
$libroId = $libroResp.id

Print-Step "Consultando disponibilidad inicial (GET /libros/$libroId)"
$libroDetalle = Invoke-RestMethod -Uri "$BaseCatalogo/libros/$libroId" -Method Get
Write-Host "Detalle: $($libroDetalle | ConvertTo-Json -Compress)"
Verify-Code 1 $libroDetalle.ejemplares_disponibles "Disponibilidad inicial es 1"

# 3. Prestamo Exitoso
Print-Title "3. PRESTAMO EXITOSO (DESCUENTO DE STOCK)"

Print-Step "Registrando prestamo para 'usuario_prueba' (POST /prestamos)"
$prestamoBody = @{ libro_id = $libroId; usuario = "usuario_prueba"; ci = "12345678" } | ConvertTo-Json
$prestamoResp = Invoke-RestMethod -Uri "$BasePrestamos/prestamos" -Method Post -ContentType "application/json" -Body $prestamoBody
Write-Host "Prestamo registrado: $($prestamoResp | ConvertTo-Json -Compress)"
$prestamoId = $prestamoResp.id

Print-Step "Verificando decremento en Catalogo (GET /libros/$libroId)"
$libroAfter = Invoke-RestMethod -Uri "$BaseCatalogo/libros/$libroId" -Method Get
Write-Host "Stock actualizado: $($libroAfter | ConvertTo-Json -Compress)"
Verify-Code 0 $libroAfter.ejemplares_disponibles "Disponibilidad reducida a 0 y estado AGOTADO"

# 4. Prestamo Fallido por Stock Agotado (409)
Print-Title "4. INTENTO DE PRESTAMO SIN STOCK (HTTP 409)"

Print-Step "Intentando solicitar libro sin stock..."
try {
    $failBody = @{ libro_id = $libroId; usuario = "otro_usuario"; ci = "87654321" } | ConvertTo-Json
    Invoke-RestMethod -Uri "$BasePrestamos/prestamos" -Method Post -ContentType "application/json" -Body $failBody
    Write-Host "[ERROR] Debio retornar error 409" -ForegroundColor Red
} catch {
    $statusCode = [int]$_.Exception.Response.StatusCode
    Verify-Code 409 $statusCode "Rechazo de prestamo sin stock con HTTP 409"
}

# 5. Devolucion
Print-Title "5. DEVOLUCION Y REPOSICION DE STOCK"

if ($prestamoId) {
    Print-Step "Registrando devolucion del prestamo $prestamoId (PUT /prestamos/$prestamoId/devolucion)"
    $devResp = Invoke-RestMethod -Uri "$BasePrestamos/prestamos/$prestamoId/devolucion" -Method Put
    Write-Host "Devolucion: $($devResp | ConvertTo-Json -Compress)"

    Print-Step "Verificando reposicion en Catalogo (GET /libros/$libroId)"
    $libroRest = Invoke-RestMethod -Uri "$BaseCatalogo/libros/$libroId" -Method Get
    Write-Host "Libro restablecido: $($libroRest | ConvertTo-Json -Compress)"
    Verify-Code 1 $libroRest.ejemplares_disponibles "Disponibilidad restablecida a 1"
}

# 6. Notificaciones
Print-Title "6. HISTORIAL DE NOTIFICACIONES"

Print-Step "Consultando notificaciones registradas (GET /notificaciones)"
$notifs = Invoke-RestMethod -Uri "$BaseNotificaciones/notificaciones" -Method Get
Write-Host "Notificaciones: $($notifs | ConvertTo-Json -Compress)"

Print-Title "PRUEBAS CONCLUIDAS SATISFACTORIAMENTE"
