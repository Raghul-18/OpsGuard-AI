@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND_URL=http://127.0.0.1:8000"
set "FRONTEND_URL=http://127.0.0.1:3000"
rem Next.js reads NEXT_PUBLIC_* when the dev server starts
set "NEXT_PUBLIC_API_URL=%BACKEND_URL%"

cd /d "%ROOT%"

if not exist ".env" (
  echo Missing backend .env file at "%ROOT%.env"
  echo Create it before starting OpsGuard.
  pause
  exit /b 1
)

set "VENV_PY="
if exist "%ROOT%.venv\Scripts\python.exe" set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
if not defined VENV_PY if exist "%ROOT%venv\Scripts\python.exe" set "VENV_PY=%ROOT%venv\Scripts\python.exe"
if not defined VENV_PY (
  echo No virtual environment found.
  echo Create one in the repo root, for example:  py -m venv .venv
  echo Then:  .venv\Scripts\activate  and  pip install -r requirements.txt
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo npm was not found on PATH.
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo Installing frontend dependencies...
  pushd "frontend"
  call npm install
  if errorlevel 1 (
    popd
    echo npm install failed.
    pause
    exit /b 1
  )
  popd
)

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if errorlevel 1 (
  echo Starting OpsGuard backend on %BACKEND_URL%
  rem Avoid nested quotes inside cmd /k "..." — they break the string after cd /d
  start "OpsGuard Backend" cmd /k cd /d "%ROOT%" ^&^& "%VENV_PY%" -m uvicorn api.main:app --host 127.0.0.1 --port 8000
) else (
  echo Backend already running on %BACKEND_URL%
)

netstat -ano | findstr /R /C:":3000 .*LISTENING" >nul
if errorlevel 1 (
  echo Starting OpsGuard frontend on %FRONTEND_URL%
  start "OpsGuard Frontend" cmd /k cd /d "%ROOT%frontend" ^&^& npm run dev -- -H 127.0.0.1 -p 3000
) else (
  echo Frontend already running on %FRONTEND_URL%
)

echo.
echo OpsGuard is starting.
echo Backend:  %BACKEND_URL%
echo Frontend: %FRONTEND_URL%
echo.
powershell -NoProfile -Command "Start-Sleep -Seconds 5" >nul
start "" "%FRONTEND_URL%"

endlocal
