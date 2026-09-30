@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

rem Usa python se existir; senao tenta o launcher py do Windows.
set PY=python
where python >nul 2>nul || set PY=py
where %PY% >nul 2>nul || (
  echo Python nao encontrado. Instale o Python 3.11 ou superior e marque Add to PATH.
  pause
  exit /b 1
)

%PY% -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo Falha ao instalar dependencias.
  pause
  exit /b 1
)

%PY% run_pipeline.py --servir
pause
