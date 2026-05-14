@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND_URL=http://127.0.0.1:8000"
set "FRONTEND_URL=http://127.0.0.1:3000"

cd /d "%ROOT%"

if not exist ".env" (
  echo Missing backend .env file at "%ROOT%.env"
  echo Create it before starting OpsGuard.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH.
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
  start "OpsGuard Backend" cmd /k "cd /d "%ROOT%" && python -m uvicorn api.main:app --host 127.0.0.1 --port 8000"
) else (
  echo Backend already running on %BACKEND_URL%
)

netstat -ano | findstr /R /C:":3000 .*LISTENING" >nul
if errorlevel 1 (
  echo Starting OpsGuard frontend on %FRONTEND_URL%
  start "OpsGuard Frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"
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
