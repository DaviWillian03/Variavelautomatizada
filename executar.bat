@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Robo da Variavel
if not exist .venv (
  echo Preparando o robo pela primeira vez...
  py -3 -m venv .venv || python -m venv .venv
)
.venv\Scripts\python -m pip install -q -r requirements.txt
if not exist .env copy .env.example .env >nul
.venv\Scripts\python -m robo
echo.
pause
