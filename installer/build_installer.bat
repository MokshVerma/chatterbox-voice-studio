@echo off
rem Builds installer\Output\ChatterboxVoiceStudio-Setup.exe with Inno Setup 6.
setlocal
set "ISCC="
for %%P in (
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do if exist %%P set "ISCC=%%~P"
if not defined ISCC (
  echo Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php or: winget install JRSoftware.InnoSetup
  exit /b 1
)
cd /d "%~dp0"
"%ISCC%" ChatterboxVoiceStudio.iss
