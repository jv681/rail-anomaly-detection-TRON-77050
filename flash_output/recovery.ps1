# STM32N6 Recovery Script
$cli   = "C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"
$el    = "C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\ExternalLoader\MX66UW1G45G_STM32N6570-DK.stldr"
$outDir= "C:\Users\hasin\Downloads\mtk3bsp2_stm32n657\flash_output"
$fsbl  = "$outDir\fsbl-trusted-fixed.bin"
$appli = "$outDir\appli-trusted.bin"

Write-Host "Waiting for board (keep holding RESET)..." -ForegroundColor Yellow
$found = $false
$tries = 0
while (-not $found -and $tries -lt 300) {
    $r = & $cli -l st-link 2>&1 | Out-String
    if ($r -match "STM32N6570-DK") { $found = $true; Write-Host "DETECTED! Flashing..." -ForegroundColor Green }
    else { Start-Sleep -Milliseconds 200; $tries++ }
}
if (-not $found) { Write-Host "TIMEOUT"; exit 1 }

Write-Host "Erasing sectors [0-3]..."
& $cli -c port=SWD freq=480 reset=HWrst -el "$el" -e [0 3] 2>&1
Write-Host "Flashing FSBL..."
& $cli -c port=SWD freq=480 reset=HWrst -el "$el" -d "$fsbl" 0x70000000 -v 2>&1
Write-Host "Flashing Appli..."
& $cli -c port=SWD freq=480 reset=HWrst -el "$el" -d "$appli" 0x71000000 -v 2>&1
Write-Host "DONE - Release RESET now!" -ForegroundColor Green
