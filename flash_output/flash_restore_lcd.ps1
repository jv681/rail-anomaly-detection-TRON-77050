# ============================================================
# flash_restore_lcd.ps1
# Restores FSBL (0x70000000) and Appli LCD 800x480 (0x70100000)
# Matches the original working output with:
#   - FSBL v10-ready
#   - LCD 800x480
#   - LL-ATON and LCD Ready. Starting live loop...
# ============================================================

$cli   = "C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"
$el    = "C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\ExternalLoader\MX66UW1G45G_STM32N6570-DK.stldr"
$fsbl  = "C:\Users\hasin\Downloads\mtk3bsp2_stm32n657\flash_output\fsbl-v10.bin"
$appli = "C:\Users\hasin\Downloads\mtk3bsp2_stm32n657\flash_output\appli-signed.bin"

Write-Host "Hold RESET button NOW. Waiting for board..." -ForegroundColor Yellow

$found = $false; $tries = 0
while (-not $found -and $tries -lt 150) {
    $r = & $cli -l st-link 2>&1 | Out-String
    if ($r -match "STM32N6") { $found = $true; Write-Host "Board detected!" -ForegroundColor Green }
    else { Start-Sleep -Milliseconds 400; $tries++ }
}
if (-not $found) { Write-Host "TIMEOUT - board not found"; exit 1 }

Write-Host "Erasing FSBL and Appli sectors [0-24]..." -ForegroundColor Yellow
& $cli -c port=SWD freq=8000 reset=HWrst -el "$el" -e [0 24] 2>&1

Write-Host "Flashing FSBL v10 -> 0x70000000..." -ForegroundColor Yellow
& $cli -c port=SWD freq=8000 reset=HWrst -el "$el" -d "$fsbl" 0x70000000 -v 2>&1

Write-Host "Flashing Appli (LCD 800x480) -> 0x70100000..." -ForegroundColor Yellow
& $cli -c port=SWD freq=8000 reset=HWrst -el "$el" -d "$appli" 0x70100000 -v 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "SUCCESS - release RESET now. Board will boot into LCD + LL-ATON live loop." -ForegroundColor Green
    Write-Host "Open Tera Term on COM9 at 115200 to view output!" -ForegroundColor Green
} else {
    Write-Host "FAILED - verify connection and retry." -ForegroundColor Red
}
