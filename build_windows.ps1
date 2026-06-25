param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# Локальное окружение держит инструменты сборки отдельно от системного Python.
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.10 -m venv .venv
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt pyinstaller

# Spec-файл хранит все параметры PyInstaller; команда остаётся короткой и повторяемой.
& $Python -m PyInstaller --clean --noconfirm KirshMangaReader.spec

if ($SkipInstaller) {
    Write-Host "EXE готов: dist\KirshMangaReader.exe"
    exit 0
}

# Inno Setup нужен только для финального setup.exe, поэтому проверяем его отдельно.
$IsccCandidates = @(
    "ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)

$Iscc = $null
foreach ($Candidate in $IsccCandidates) {
    $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
    if ($Command) {
        $Iscc = $Command.Source
        break
    }
    if (Test-Path $Candidate) {
        $Iscc = $Candidate
        break
    }
}

if (-not $Iscc) {
    Write-Warning "Inno Setup 6 не найден. Установи его и запусти скрипт снова или используй EXE: dist\KirshMangaReader.exe"
    exit 0
}

& $Iscc "installer\KirshMangaReader.iss"
Write-Host "Установщик готов: dist\installer\setup.exe"
