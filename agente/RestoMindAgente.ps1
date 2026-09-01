<#
.SYNOPSIS
    Baja los comprobantes SUNAT de RestoMind y los deja en la carpeta que
    vigila el Facturador SUNAT.

.DESCRIPTION
    Corre en la PC del restaurante, donde está instalado el Facturador.
    Consulta el servidor, escribe los cuatro archivos (.det .tri .ley .cab)
    de cada comprobante y confirma la entrega.

    Está en PowerShell y no en Python a propósito: PowerShell viene de
    fábrica en Windows, así que esta PC no necesita instalar ni mantener
    ningún runtime extra (ya tiene que sostener el Java del Facturador).

    Solo hace conexiones SALIENTES: no hay que abrir puertos en el router
    del restaurante ni montar una VPN.

.PARAMETER ConfigPath
    Ruta al config.json. Por defecto, el que esté junto a este script.

.EXAMPLE
    .\RestoMindAgente.ps1
    .\RestoMindAgente.ps1 -ConfigPath "C:\RestoMind\config.json"
    .\RestoMindAgente.ps1 -Probar     # valida la config y sale, sin escribir nada
#>

param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "config.json"),
    [switch]$Probar
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------

if (-not (Test-Path $ConfigPath)) {
    Write-Error "No se encontró la configuración en '$ConfigPath'. Copiá config.example.json a config.json y completalo."
    exit 1
}

$cfg = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json

foreach ($campo in @("url", "token", "carpetaFacturador")) {
    if ([string]::IsNullOrWhiteSpace($cfg.$campo)) {
        Write-Error "Falta '$campo' en $ConfigPath."
        exit 1
    }
}

if (-not (Test-Path $cfg.carpetaFacturador)) {
    Write-Error "La carpeta del Facturador no existe: '$($cfg.carpetaFacturador)'. Revisá 'carpetaFacturador' en $ConfigPath."
    exit 1
}

# El registro local de lo ya escrito. NO es redundante con el control del
# servidor: si el agente escribe los archivos y se corta la red antes de
# confirmar, sin este registro los volvería a escribir en la vuelta
# siguiente — y si el Facturador ya los procesó, eso puede terminar en una
# boleta emitida DOS VECES ante SUNAT. Este archivo previene la doble
# escritura; el servidor lleva aparte la vista de qué falta entregar.
$RegistroPath = Join-Path $PSScriptRoot "descargados.txt"
$LogPath      = Join-Path $PSScriptRoot "agente.log"

function Write-Log {
    param([string]$Mensaje, [string]$Nivel = "INFO")
    $linea = "{0}  [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Nivel, $Mensaje
    Write-Host $linea
    try { Add-Content -Path $LogPath -Value $linea -Encoding UTF8 } catch { }
}

function Get-YaDescargados {
    $set = [System.Collections.Generic.HashSet[string]]::new()
    if (Test-Path $RegistroPath) {
        foreach ($linea in @(Get-Content $RegistroPath)) {
            if (-not [string]::IsNullOrWhiteSpace($linea)) {
                [void]$set.Add($linea.Trim())
            }
        }
    }
    # La coma NO es un typo: sin ella PowerShell "desenrolla" la colección al
    # devolverla, y un set vacío (el caso de la primera corrida, que es
    # justamente cuando hay algo que descargar) se convierte en $null. El
    # llamador entonces revienta al invocar .Contains() sobre nada.
    return ,$set
}

$headers = @{ "X-Agente-Token" = $cfg.token }

# ---------------------------------------------------------------------
# Modo prueba: valida token y config, no escribe nada
# ---------------------------------------------------------------------

if ($Probar) {
    try {
        $ping = Invoke-RestMethod -Uri "$($cfg.url)/api/agente/ping" -Headers $headers -TimeoutSec 30
        Write-Log "Conexión OK. Restaurante: $($ping.cliente_nombre). Comprobantes pendientes: $($ping.pendientes)."
        Write-Log "Carpeta del Facturador: $($cfg.carpetaFacturador)"
        exit 0
    } catch {
        Write-Log "No se pudo conectar: $($_.Exception.Message)" "ERROR"
        exit 1
    }
}

# ---------------------------------------------------------------------
# Ciclo principal
# ---------------------------------------------------------------------

try {
    $respuesta = Invoke-RestMethod -Uri "$($cfg.url)/api/agente/pendientes" -Headers $headers -TimeoutSec 60
} catch {
    # Sin conexión no es un error del que haya que alarmarse: el
    # restaurante puede estar cerrado o sin internet. Se anota y se
    # reintenta en la próxima corrida; los comprobantes siguen esperando
    # del lado del servidor.
    Write-Log "No se pudo consultar el servidor: $($_.Exception.Message)" "AVISO"
    exit 0
}

$comprobantes = @($respuesta.comprobantes)
if ($comprobantes.Count -eq 0) {
    Write-Log "Sin comprobantes pendientes."
    exit 0
}

$yaDescargados = Get-YaDescargados
$confirmar = @()
$escritos = 0

foreach ($c in $comprobantes) {
    if ($yaDescargados.Contains($c.nombre_base)) {
        # Ya estaba en disco de una corrida anterior que no llegó a
        # confirmar. No se reescribe (el Facturador podría procesarlo de
        # nuevo), pero sí se vuelve a confirmar para sacarlo de la cola.
        Write-Log "Ya entregado antes, solo se reconfirma: $($c.numero_boleta)"
        $confirmar += $c.id
        continue
    }

    try {
        # ORDEN DELIBERADO: el .cab va ÚLTIMO. El Facturador vigila la
        # carpeta y dispara cuando aparece la cabecera, así que si fuera
        # primero podría levantar el comprobante antes de que existan su
        # detalle, sus tributos y sus leyendas. Es la misma regla que aplica
        # el servidor al escribirlos (ver backend/utils/sfs_export.py).
        foreach ($ext in @("det", "tri", "ley", "cab")) {
            $destino = Join-Path $cfg.carpetaFacturador "$($c.nombre_base).$ext"
            # WriteAllText con ASCIIEncoding y NO Out-File: Out-File antepone
            # un BOM y traduce los fines de línea, y eso rompería el CRLF
            # puro que el formato de SUNAT exige. El contenido ya viene en
            # ASCII desde el servidor (ver limpiar_texto en sfs_export.py).
            [System.IO.File]::WriteAllText($destino, $c.$ext, [System.Text.ASCIIEncoding]::new())
        }

        # Se anota ANTES de confirmar: si el proceso muere entre la
        # escritura y la confirmación, la próxima corrida tiene que saber
        # que estos archivos ya están en la carpeta.
        Add-Content -Path $RegistroPath -Value $c.nombre_base -Encoding ASCII
        $confirmar += $c.id
        $escritos++
        Write-Log "Entregado: $($c.numero_boleta)"
    } catch {
        # Un comprobante que falla no frena a los demás: los que sí se
        # escribieron se confirman igual, y este vuelve a aparecer en la
        # próxima vuelta.
        Write-Log "No se pudo escribir $($c.numero_boleta): $($_.Exception.Message)" "ERROR"
    }
}

if ($confirmar.Count -gt 0) {
    try {
        $body = @{ ids = $confirmar } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri "$($cfg.url)/api/agente/confirmar" -Method Post `
            -Headers $headers -Body $body -ContentType "application/json" -TimeoutSec 30 | Out-Null
        Write-Log "$escritos comprobante(s) entregado(s) y confirmado(s)."
    } catch {
        # Los archivos YA están en la carpeta y anotados en el registro
        # local. Que falle la confirmación solo significa que el servidor
        # los va a volver a ofrecer; la próxima corrida los reconoce por el
        # registro, no los reescribe, y reconfirma.
        Write-Log "Archivos entregados pero no se pudo confirmar al servidor: $($_.Exception.Message)" "AVISO"
    }
}
