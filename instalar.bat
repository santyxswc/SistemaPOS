@echo off
rem Instalacion del punto de venta en Windows. Se ejecuta una sola vez.
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo No se encontro Python. Instale Python 3.11 o superior desde https://www.python.org/downloads/
  echo y marque la opcion "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo Preparando el entorno...
  py -3 -m venv .venv || goto :error
)
.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto :error

if not exist src\pos\presentation\web\static\index.html (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo AVISO: falta la interfaz compilada y no hay Node.js para compilarla.
    echo Use un paquete de instalacion que ya la incluya.
  ) else (
    echo Compilando la interfaz...
    pushd frontend
    call npm ci --no-audit --no-fund || goto :error
    call npm run build || goto :error
    popd
  )
)

.venv\Scripts\python.exe manage.py init || goto :error
echo.
echo Instalacion terminada. Para usar el sistema haga doble clic en iniciar-pos.bat
pause
exit /b 0

:error
echo.
echo La instalacion fallo. Revise el mensaje anterior.
pause
exit /b 1
