export CORS_ALLOW_ORIGIN="http://localhost:5050;http://localhost:5051;http://localhost:5173;http://localhost:8080;http://127.0.0.1:5050;http://127.0.0.1:5051;http://127.0.0.1:5173;http://127.0.0.1:8080"
PORT="${PORT:-8080}"

# WEBUI_SECRET_KEY 自 v0.9.6 起为硬性要求;首次运行自动生成并持久化到 .webui_secret_key
KEY_FILE="$(dirname "$0")/.webui_secret_key"
if [ -z "$WEBUI_SECRET_KEY" ]; then
  if [ ! -f "$KEY_FILE" ]; then
    python -c "import base64,os; print(base64.b64encode(os.urandom(48)).decode())" > "$KEY_FILE"
    echo "Generated new WEBUI_SECRET_KEY at $KEY_FILE"
  fi
  WEBUI_SECRET_KEY="$(cat "$KEY_FILE")"
fi
export WEBUI_SECRET_KEY

uvicorn open_webui.main:app --port $PORT --host 0.0.0.0 --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}" --reload
