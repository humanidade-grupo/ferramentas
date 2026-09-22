@echo off
rem ============================================================================
rem  Atualizar D4Sign — a passada MANUAL, para o Ricardo clicar.
rem
rem  Existe porque a sessao da D4Sign cai quase todo dia e a passada agendada
rem  (8h, 14h e 20h) aborta sozinha: quando isso acontece, ninguem esta olhando,
rem  e o espelho envelhece. Aqui a janela do Edge SEMPRE aparece:
rem  se pedir login, e so entrar na janela; o resto segue sozinho.
rem
rem  A janela do prompt fica aberta no fim (pause) para dar tempo de ler o
rem  resultado: quantos documentos foram gravados, ou por que abortou.
rem ============================================================================
chcp 65001 >nul
cd /d "%~dp0"
title Atualizar D4Sign - espelho de contratos no Cofre

set "PY=C:\Users\ricar\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=py"

echo.
echo  Atualizando o espelho da D4Sign no Cofre do Parque...
echo  (se abrir a tela de login da D4Sign, faca o login na janela do Edge)
echo.

"%PY%" -X utf8 status.py
set ERRO=%ERRORLEVEL%

echo.
if "%ERRO%"=="0" (
  echo  ======================================================================
  echo   PRONTO. O espelho foi gravado no Cofre — a PonteApp ja mostra o novo.
  echo  ======================================================================
) else (
  echo  ======================================================================
  echo   NAO GRAVOU. O motivo esta na ultima linha acima e no status_log.csv.
  echo   Nada foi estragado: o espelho ficou como estava.
  echo  ======================================================================
)
echo.
pause
