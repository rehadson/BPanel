@echo off
setlocal

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PYTHON=python"
  ) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
      set "PYTHON=py"
    ) else (
      echo Could not find a Python interpreter ^(no .venv, no "python", no "py"^).
      echo Install Python from https://www.python.org/downloads/ and make sure
      echo "Add python.exe to PATH" is checked during installation.
      pause
      exit /b 1
    )
  )
)

echo Using: %PYTHON%
"%PYTHON%" app.py
set "EXITCODE=%errorlevel%"

if not "%EXITCODE%"=="0" (
  echo.
  echo The app closed with an error ^(exit code %EXITCODE%^). See the message above.
  echo If it mentions a missing module, run:  %PYTHON% -m pip install -r requirements.txt
  pause
)

endlocal
