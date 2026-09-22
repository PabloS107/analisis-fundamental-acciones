@echo off
title Servidor de Analisis Fundamental - Django
echo ========================================================
echo Iniciando Terminal de Analisis Fundamental (Django)...
echo ========================================================

set "APP_DIR=%~dp0web_dashboard"
if not exist "%APP_DIR%" (
    set "APP_DIR=c:\Users\pablo\OneDrive\Documents\Analisis fundamental de acciones\web_dashboard"
)

echo Directorio de la aplicacion: %APP_DIR%
echo Abriendo navegador en http://127.0.0.1:8000 ...
cd /d "%APP_DIR%"
start "" http://127.0.0.1:8000/
python manage.py runserver 127.0.0.1:8000
pause
