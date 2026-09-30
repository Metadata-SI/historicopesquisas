@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PY=python
where python >nul 2>nul || set PY=py
%PY% -m pip install -q -r requirements.txt
rem Baixa os dados do Plano Politico e sobe o site logo em seguida (sem a coleta demorada dos portais).
%PY% -m coleta.planopolitico
%PY% run_pipeline.py --offline --skip-model --servir
pause
