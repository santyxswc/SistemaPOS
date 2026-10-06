@echo off
rem Copia de seguridad de la base de datos en data\backups (conserva las ultimas 30).
rem Para programarla todos los dias a las 10 p. m., ejecute una vez en una consola
rem (cambie C:\POS por la carpeta donde esta instalado el sistema):
rem   schtasks /create /tn "POS respaldo" /sc daily /st 22:00 /tr "C:\POS\respaldo.bat"
cd /d "%~dp0"
.venv\Scripts\python.exe manage.py backup
