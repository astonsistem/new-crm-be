import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.core.logging import get_logger

logger = get_logger("app.http")

# Status codes that should be logged at WARNING level
_WARN_CODES = {400, 401, 403, 404, 405, 409, 410, 422, 429}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log every HTTP request/response with:
      - request_id  (UUID per request)
      - method & path
      - status code
      - elapsed time (ms)
      - client IP
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        # Attach request_id to request state so routers can reference it
        request.state.request_id = request_id

        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )

        logger.debug(
            "[%s] --> %s %s  (client=%s)",
            request_id,
            request.method,
            request.url.path,
            client_ip,
        )

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "[%s] 500 INTERNAL SERVER ERROR  %s %s  %.1f ms  (client=%s)  error=%r",
                request_id,
                request.method,
                request.url.path,
                elapsed_ms,
                client_ip,
                exc,
            )
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        status_code = response.status_code

        log_line = (
            "[%s] %s %s %s  %.1f ms  (client=%s)",
            request_id,
            request.method,
            request.url.path,
            status_code,
            elapsed_ms,
            client_ip,
        )

        if status_code >= 500:
            logger.error(*log_line)
        elif status_code in _WARN_CODES:
            logger.warning(*log_line)
        else:
            logger.info(*log_line)

        # Attach request_id to response header for easier debugging
        response.headers["X-Request-ID"] = request_id
        return response
