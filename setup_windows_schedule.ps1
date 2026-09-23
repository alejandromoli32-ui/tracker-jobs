<#
.SYNOPSIS
    Registra una tarea programada en Windows para ejecutar la búsqueda diaria de vacantes a las 7:00 AM.
.DESCRIPTION
    Crea la tarea 'JobHunter_Actualizacion_Diaria' en el Programador de Tareas de Windows.
    Ejecuta run_daily_update.bat en segundo plano o visible según preferencia.
#>

$TaskName = "JobHunter_Actualizacion_Diaria"
$WorkingDirectory = $PSScriptRoot
$BatPath = Join-Path $WorkingDirectory "run_daily_update.bat"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "    PROGRAMADOR DE TAREA DIARIA - JOB HUNTER AI" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Ruta del script: $BatPath" -ForegroundColor Gray
Write-Host "Hora programada: 07:00 AM todos los dias" -ForegroundColor Gray

# Verificar si schtasks.exe puede registrar la tarea diaria
$SchtasksCmd = "schtasks /Create /SC DAILY /TN `"$TaskName`" /TR `"`"$BatPath`"`" /ST 07:00 /F"

try {
    Invoke-Expression $SchtasksCmd
    Write-Host "`n[EXITO] Tarea programada registrada exitosamente como '$TaskName'." -ForegroundColor Green
    Write-Host "La busqueda de vacantes se ejecutara todos los dias a las 7:00 AM de forma automatica." -ForegroundColor Green
} catch {
    Write-Host "`n[AVISO] No se pudo registrar automaticamente la tarea: $_" -ForegroundColor Yellow
    Write-Host "Puedes ejecutar manualmente 'run_daily_update.bat' con doble clic en cualquier momento." -ForegroundColor Gray
}

Write-Host "`nPresiona cualquier tecla para continuar..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
