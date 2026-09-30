@echo off
rem Thin wrapper for the double-click entries. All decisions live in win\launch.py, because
rem cmd.exe expands %ERRORLEVEL% at parse time inside blocks and mishandles quoted paths.
rem Keep this file ASCII only: cmd reads it in the console codepage.
setlocal EnableExtensions
cd /d "%~dp0.."

set "PY=C:\Python314\python.exe"
if not exist "%PY%" (
    echo Python was not found at "%PY%".
    echo Open this file in an editor, point PY to your python.exe, then run it again.
    pause
    exit /b 1
)

"%PY%" "win\launch.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo Launcher stopped with code %RC%.
    pause
)
exit /b %RC%
