@echo off
rem Fullscreen playback. Windowed entry: see the other .cmd. Shared logic: win\launch.cmd
cd /d "%~dp0."
call "win\launch.cmd" full
