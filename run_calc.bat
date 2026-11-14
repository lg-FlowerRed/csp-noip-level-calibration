@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON=python"
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON=py"

%PYTHON% -c "import numpy, scipy" >nul 2>nul
if errorlevel 1 (
    echo 缺少 NumPy 或 SciPy，请先运行 install_python.bat，或执行：
    echo   %PYTHON% -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

%PYTHON% -X utf8 calc_rating_matched.py %*
set "RESULT=%errorlevel%"
echo.
pause
exit /b %RESULT%
