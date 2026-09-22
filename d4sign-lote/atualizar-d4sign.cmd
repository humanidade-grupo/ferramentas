@echo off
rem ============================================================================
rem  Atualizar D4Sign - a passada MANUAL, para o Ricardo clicar.
rem
rem  Existe porque a sessao da D4Sign cai quase todo dia e a passada agendada
rem  (8h, 14h e 20h) aborta sozinha: quando isso acontece ninguem esta olhando,
rem  e o espelho envelhece. Aqui a janela do Edge aparece e, se pedir login,
rem  o script espera voce logar (este arquivo roda com console, por isso ele
rem  espera; a tarefa agendada aborta em segundos, de proposito).
rem
rem  ATENCAO A QUEM EDITAR: salve SEMPRE com CRLF e sem acento. Com LF o cmd.exe
rem  come o primeiro caractere de cada linha (22/09/2026).
rem
rem  Argumentos passam direto: atualizar-d4sign.cmd --dry-run
rem ============================================================================
cd /d "%~dp0"
title Atualizar D4Sign - espelho de contratos no Cofre

set "PY=C:\Users\ricar\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=py"

echo.
echo  Atualizando o espelho da D4Sign no Cofre do Parque...
echo  (se abrir a tela de login da D4Sign, faca o login na janela do Edge)
echo  Leva cerca de 10 minutos. Pode deixar rodando.
echo.

"%PY%" -X utf8 status.py %*
set ERRO=%ERRORLEVEL%

echo.
if "%ERRO%"=="0" goto :ok
echo  ======================================================================
echo   NAO GRAVOU. O motivo esta nas linhas acima e no status_log.csv.
echo   Nada foi estragado: o espelho ficou como estava.
echo  ======================================================================
goto :fim
:ok
echo  ======================================================================
echo   PRONTO. O espelho foi gravado no Cofre - a PonteApp ja mostra o novo.
echo  ======================================================================
:fim
echo.
pause
