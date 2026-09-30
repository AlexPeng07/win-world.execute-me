@echo off
rem Windowed playback: maximized, so the Windows taskbar stays visible.
rem Alt+Enter toggles fullscreen at any time while it plays.
rem Edit win\launch.cmd and pass "win" instead of "max" for a plain resizable window.
cd /d "%~dp0."
call "win\launch.cmd" max
