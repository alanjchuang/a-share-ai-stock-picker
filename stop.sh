#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

stop_pid() {
  local pid_file="$1"
  local name="$2"
  if [ -f "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid"
      echo "==> 已停止 $name，PID $pid"
    fi
    rm -f "$pid_file"
  else
    echo "==> $name 未找到PID文件"
  fi
}

stop_pid "$ROOT_DIR/backend/.backend.pid" "后端"
stop_pid "$ROOT_DIR/frontend/.frontend.pid" "前端"

stop_port() {
  local port="$1"
  local name="$2"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
    echo "==> 已停止${name}端口 $port 进程 $pid"
  done
}

if command -v screen >/dev/null 2>&1; then
  sessions="$(screen -ls | awk '/astock-(backend|frontend)/ {print $1}' || true)"
  for session_name in $sessions; do
    if [[ "$session_name" == *"astock-backend"* ]]; then
      screen -S "$session_name" -X quit || true
      echo "==> 已停止后端screen会话 $session_name"
    elif [[ "$session_name" == *"astock-frontend"* ]]; then
      screen -S "$session_name" -X quit || true
      echo "==> 已停止前端screen会话 $session_name"
    fi
  done
fi

stop_port 8000 "后端"
stop_port 5173 "前端"
