#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "==> A股多因子智能选股Web系统启动中"

pick_python() {
  for candidate in python3.13 python3.12 python3.11 python3.10 /Users/bytedance/miniconda3/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      local version
      version="$("$candidate" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
      if "$candidate" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
      then
        echo "$candidate"
        return 0
      fi
    fi
  done
  echo "未找到 Python 3.10+，请先安装 Python 3.10 或更高版本。" >&2
  return 1
}

PYTHON_BIN="$(pick_python)"
echo "==> 使用 Python：$PYTHON_BIN"

cd "$BACKEND_DIR"
if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if lsof -tiTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "==> 后端端口8000已有服务在运行"
elif command -v screen >/dev/null 2>&1; then
  if screen -ls | grep -q "astock-backend"; then
    echo "==> 后端screen会话已在运行"
  else
    screen -dmS astock-backend bash -lc "cd \"$BACKEND_DIR\" && source .venv/bin/activate && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1"
    echo "==> 后端已启动：http://127.0.0.1:8000/docs"
  fi
elif [ -f ".backend.pid" ] && kill -0 "$(cat .backend.pid)" 2>/dev/null; then
  echo "==> 后端已在运行，PID $(cat .backend.pid)"
else
  nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
  echo $! > .backend.pid
  echo "==> 后端已启动：http://127.0.0.1:8000/docs"
fi

cd "$FRONTEND_DIR"
npm install
if lsof -tiTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "==> 前端端口5173已有服务在运行"
elif command -v screen >/dev/null 2>&1; then
  if screen -ls | grep -q "astock-frontend"; then
    echo "==> 前端screen会话已在运行"
  else
    screen -dmS astock-frontend bash -lc "cd \"$FRONTEND_DIR\" && npm run dev > frontend.log 2>&1"
    echo "==> 前端已启动：http://127.0.0.1:5173"
  fi
elif [ -f ".frontend.pid" ] && kill -0 "$(cat .frontend.pid)" 2>/dev/null; then
  echo "==> 前端已在运行，PID $(cat .frontend.pid)"
else
  nohup npm run dev > frontend.log 2>&1 &
  echo $! > .frontend.pid
  echo "==> 前端已启动：http://127.0.0.1:5173"
fi

echo "==> 完成。日志：backend/backend.log 与 frontend/frontend.log"
