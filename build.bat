@echo off
REM ============================================================
REM Build script for "Consolidador de Cuentas Corrientes"
REM Produces dist\ConsolidadorCCTT.exe via PyInstaller
REM ============================================================

setlocal ENABLEEXTENSIONS

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta en el PATH.
    exit /b 1
)

echo [1/3] Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Falla instalando dependencias.
    exit /b 1
)

echo [2/3] Limpiando build anterior...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist ConsolidadorCCTT.spec del /q ConsolidadorCCTT.spec

echo [3/3] Ejecutando PyInstaller...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name ConsolidadorCCTT ^
    --collect-submodules app ^
    --collect-submodules pdfplumber ^
    --collect-submodules pdfminer ^
    --collect-submodules openpyxl ^
    --collect-submodules pandas ^
    app\main.py

if errorlevel 1 (
    echo [ERROR] PyInstaller fallo.
    exit /b 1
)

echo.
echo === OK === ejecutable disponible en dist\ConsolidadorCCTT.exe
endlocal
