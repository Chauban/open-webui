@echo off
cd /d "%~dp0backend"
set CORS_ALLOW_ORIGIN=http://localhost:5050;http://localhost:5051;http://localhost:5173;http://localhost:8080;http://127.0.0.1:5050;http://127.0.0.1:5051;http://127.0.0.1:5173;http://127.0.0.1:8080
rem Default UI language for browsers without a saved locale
set DEFAULT_LOCALE=zh-CN

rem WEBUI_SECRET_KEY is required since v0.9.6; auto-generate once and reuse
if not exist ".webui_secret_key" (
  .venv\Scripts\python.exe -c "import base64,os;open('.webui_secret_key','w').write(base64.b64encode(os.urandom(48)).decode())"
  echo Generated new WEBUI_SECRET_KEY at .webui_secret_key
)
set /p WEBUI_SECRET_KEY=<.webui_secret_key

.venv\Scripts\python.exe -m uvicorn open_webui.main:app --port 8080 --host 0.0.0.0 --reload

echo.
echo Backend exited with code %ERRORLEVEL%.
pause
