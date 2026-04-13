from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Request
from fastapi.responses import JSONResponse
from redis import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import logger


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):  # type: ignore[override]
        request_id = request.headers.get('x-request-id') or f'req-{datetime.now(UTC).timestamp()}'
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers['x-request-id'] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._memory_buckets: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        try:
            self.redis = Redis(host=settings.redis_host, port=settings.redis_port, db=settings.redis_db)
            self.redis.ping()
        except Exception:
            self.redis = None
            logger.warning('rate_limit.redis_unavailable')

    async def dispatch(self, request: Request, call_next: Callable):  # type: ignore[override]
        client_ip = request.client.host if request.client else 'unknown'
        minute_bucket = int(datetime.now(UTC).timestamp() // 60)
        key = f'ratelimit:{client_ip}:{minute_bucket}'

        allowed = True
        if self.redis:
            count = self.redis.incr(key)
            if count == 1:
                self.redis.expire(key, 60)
            allowed = count <= settings.api_rate_limit_per_minute
        else:
            count, bucket = self._memory_buckets[client_ip]
            if bucket != minute_bucket:
                count = 0
            count += 1
            self._memory_buckets[client_ip] = (count, minute_bucket)
            allowed = count <= settings.api_rate_limit_per_minute

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    'error': {
                        'code': 'RATE_LIMIT_EXCEEDED',
                        'message': 'Muitas requisicoes. Tente novamente em instantes.',
                        'details': {},
                    }
                },
            )

        return await call_next(request)
