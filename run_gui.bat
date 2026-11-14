@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON=python"
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON=py"

%PYTHON% -c "import numpy, scipy, tkinter" >nul 2>nul
if errorlevel 1 (
    echo 请安装 NumPy、SciPy 以及 Python 自带的 Tcl/Tk：
    echo   %PYTHON% -m pip install -r requirements.txt
    echo 缺少 Tcl/Tk 时，请重新运行官方 Python 安装器，添加 Tcl/Tk 组件。
    echo.
    pause
    exit /b 1
)

%PYTHON% -X utf8 calc_rating_gui.py
set "RESULT=%errorlevel%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
