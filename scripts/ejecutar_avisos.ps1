# =============================================================================
# scripts/ejecutar_avisos.ps1
# Invoca la revisión periódica de vencimientos y reenvío de multas en Préstamos.
# =============================================================================

[CmdletBinding()]
param(
    [string]$BaseUrl = $env:BASE_URL,
    [string]$AuthUser = $env:BASIC_AUTH_USER,
    [string]$AuthPassword = $env:BASIC_AUTH_PASSWORD
)

$ErrorActionPreference = "Stop"

if (-not $BaseUrl) {
    $BaseUrl = "http://127.0.0.1:8002"
}
$BaseUrl = $BaseUrl.TrimEnd('/')
$Endpoint = "$BaseUrl/prestamos/revisar-vencimientos"

$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$Timestamp] Iniciando revisión de vencimientos en: $Endpoint"

$Headers = @{
    "Content-Type" = "application/json"
}

if ($AuthUser -and $AuthPassword) {
    $Bytes = [System.Text.Encoding]::UTF8.GetBytes("${AuthUser}:${AuthPassword}")
    $Base64 = [Convert]::ToBase64String($Bytes)
    $Headers["Authorization"] = "Basic $Base64"
}

try {
    $Response = Invoke-WebRequest -Uri $Endpoint -Method Post -Headers $Headers -UseBasicParsing
    $StatusCode = [int]$Response.StatusCode
    $Content = $Response.Content

    Write-Host "HTTP Code: $StatusCode"
    Write-Host "Respuesta: $Content"

    if ($StatusCode -ne 200) {
        Write-Error "La revisión de vencimientos falló con código HTTP: $StatusCode"
        exit 1
    }

    Write-Host "[SUCCESS] Revisión de vencimientos completada satisfactoriamente."
    exit 0
}
catch [System.Net.WebException] {
    $Ex = $_.Exception
    if ($Ex.Response) {
        $StatusCode = [int]$Ex.Response.StatusCode
        $Stream = $Ex.Response.GetResponseStream()
        $Reader = New-Object System.IO.StreamReader($Stream)
        $Content = $Reader.ReadToEnd()
        Write-Host "HTTP Code: $StatusCode"
        Write-Host "Respuesta: $Content"
        Write-Error "La revisión de vencimientos falló con código HTTP: $StatusCode"
    } else {
        Write-Error "No se pudo conectar con el servicio: $($Ex.Message)"
    }
    exit 1
}
catch {
    Write-Error "Error ejecutando revisión: $($_.Exception.Message)"
    exit 1
}

