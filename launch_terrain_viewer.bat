@echo off
REM Launch the LEM Terrain Viewer from a Windows shell.
REM Usage:
REM   launch_terrain_viewer.bat                     (opens with File > Open dialog)
REM   launch_terrain_viewer.bat output\elevation.npy (opens a specific file)
REM   launch_terrain_viewer.bat output\              (opens a directory of .npy files)

setlocal EnableExtensions

set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "LAUNCHER=%REPO_ROOT%\scripts\launch_terrain_viewer.pyw"
set "WINDOWS_ENV=%REPO_ROOT%\lem-env-win"
set "WINDOWS_PYTHON=%WINDOWS_ENV%\Scripts\python.exe"
set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"
set "EXITCODE=0"

if not exist "%LAUNCHER%" (
    echo [LEM] Could not find the launcher script:
    echo [LEM]   %LAUNCHER%
    echo [LEM] Make sure you are running this file from the repository checkout.
    pause
    exit /b 1
)

if not exist "%WINDOWS_PYTHON%" (
    call :create_windows_env
    set "EXITCODE=%ERRORLEVEL%"
    if not "%EXITCODE%"=="0" goto :finish
)

call :ensure_runtime_dependencies
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" goto :finish

"%WINDOWS_PYTHON%" "%LAUNCHER%" %*
set "EXITCODE=%ERRORLEVEL%"
goto :finish

:create_windows_env
echo [LEM] Creating repo-local Windows environment at:
echo [LEM]   %WINDOWS_ENV%

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv "%WINDOWS_ENV%"
    exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if not errorlevel 1 (
    python -m venv "%WINDOWS_ENV%"
    exit /b %ERRORLEVEL%
)

echo [LEM] Could not find a usable Python interpreter.
echo [LEM] Tried:
echo [LEM]   - py -3
echo [LEM]   - python
echo [LEM] Install Python 3.12+ on Windows, then rerun this launcher.
exit /b 9009

:ensure_runtime_dependencies
"%WINDOWS_PYTHON%" -c "import numpy, PySide6, pyqtgraph, OpenGL" >nul 2>nul
if not errorlevel 1 exit /b 0

echo [LEM] Installing viewer dependencies into:
echo [LEM]   %WINDOWS_ENV%
"%WINDOWS_PYTHON%" -m pip install -e "%REPO_ROOT%"
if errorlevel 1 (
    echo [LEM] Failed to install viewer dependencies into the repo-local Windows environment.
    echo [LEM] Check the pip output above for the exact failure.
    exit /b 1
)

"%WINDOWS_PYTHON%" -c "import numpy, PySide6, pyqtgraph, OpenGL" >nul 2>nul
if not errorlevel 1 exit /b 0

echo [LEM] Viewer dependencies were installed, but the runtime import probe still failed.
echo [LEM] Check the Python environment at:
echo [LEM]   %WINDOWS_ENV%
exit /b 1

:finish
if not "%EXITCODE%"=="0" (
    echo.
    echo [LEM] Terrain viewer failed to start. See the error details above.
    echo [LEM] This window will stay open so you can read the message.
    pause
)
exit /b %EXITCODE%
