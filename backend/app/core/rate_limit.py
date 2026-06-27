from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    """轻量限流：避免前端误操作导致第三方数据源被高频调用。"""

    def __init__(self, app: Callable, max_requests: int = 180, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clients: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client = request.client.host if request.client else "local"
        now = time.time()
        queue = self.clients[client]
        while queue and now - queue[0] > self.window_seconds:
            queue.popleft()
        if len(queue) >= self.max_requests:
            return JSONResponse({"code": 429, "message": "请求过于频繁，请稍后再试", "data": None}, status_code=429)
        queue.append(now)
        return await call_next(request)
