@echo off
rem Inicia el punto de venta y abre el navegador. Deje esta ventana abierta mientras trabaja.
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Primero ejecute instalar.bat
  pause
  exit /b 1
)
echo Punto de venta en marcha. No cierre esta ventana mientras use el sistema.
.venv\Scripts\python.exe manage.py start
pause
