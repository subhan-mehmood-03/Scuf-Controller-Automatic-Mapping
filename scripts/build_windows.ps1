$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Windows is required for this build.' }
Push-Location (Join-Path $PSScriptRoot '..')
try {
    python -m PyInstaller --noconfirm --clean SCUF-Automatic-Mapping.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    $process = Start-Process -FilePath (Join-Path $PWD 'dist/SCUF-Automatic-Mapping.exe') -ArgumentList '--self-test' -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "Packaged smoke test failed: $($process.ExitCode)" }
    $env:QT_QPA_PLATFORM = 'offscreen'
    $guiProcess = Start-Process -FilePath (Join-Path $PWD 'dist/SCUF-Automatic-Mapping.exe') -ArgumentList '--gui-smoke' -Wait -PassThru -WindowStyle Hidden
    if ($guiProcess.ExitCode -ne 0) { throw "Packaged GUI smoke test failed: $($guiProcess.ExitCode)" }
    Write-Output 'Built dist/SCUF-Automatic-Mapping.exe; packaged self-test passed.'
} finally { Pop-Location }
