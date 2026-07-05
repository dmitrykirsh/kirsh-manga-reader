@echo off
chcp 65001 >nul
echo ========================================
echo   Kirsh Manga Reader - Сборка EXE
echo ========================================
echo.

set PYBIN=C:\Users\dkirs\AppData\Local\Python\pythoncore-3.14-64\Scripts\pyinstaller.exe

REM Проверяем наличие pyinstaller
if not exist "%PYBIN%" (
    echo [ОШИБКА] PyInstaller не найден по пути: %PYBIN%
    echo.
    echo Попробуйте установить: py -m pip install pyinstaller
    pause
    exit /b 1
)

REM Удаляем старые сборки
if exist dist (
    echo Удаление старой папки dist...
    rmdir /s /q dist
)
if exist build (
    echo Удаление старой папки build...
    rmdir /s /q build
)

echo.
echo Начинаю сборку...
echo.

REM Сборка
%PYBIN% --onefile --windowed --name "KirshMangaReader" --icon="icon.ico" --add-data "icon.ico;." --add-data "UnRAR.exe;." --hidden-import "rarfile" --hidden-import "selenium" --hidden-import "webdriver_manager" --hidden-import "natsort" --hidden-import "PyQt6" mr.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   ✅ СБОРКА УСПЕШНА!
    echo ========================================
    echo.
    echo Файл: dist\KirshMangaReader.exe
    echo Размер: 
    dir dist\KirshMangaReader.exe | find "KirshMangaReader.exe"
    echo.
) else (
    echo.
    echo ========================================
    echo   ❌ ОШИБКА СБОРКИ
    echo ========================================
    echo Проверьте консоль выше для деталей.
)

pause