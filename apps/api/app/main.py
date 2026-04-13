from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.logging import configure_logging, logger
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.db.session import SessionLocal

try:
    import sentry_sdk
except Exception:  # pragma: no cover
    sentry_sdk = None

configure_logging()

if settings.sentry_dsn and sentry_sdk:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        environment=settings.app_env,
        release='odontoflux@1.0.0',
    )

app = FastAPI(
    title='OdontoFlux API',
    version='1.0.0',
    docs_url='/api/v1/docs',
    redoc_url='/api/v1/redoc',
    openapi_url='/api/v1/openapi.json',
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content=exc.as_dict())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': 'Entrada invalida',
                'details': {'errors': exc.errors()},
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception(
        'unhandled_error',
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            'error': {
                'code': 'INTERNAL_SERVER_ERROR',
                'message': 'Erro interno inesperado',
                'details': {},
            }
        },
    )


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'api', 'env': settings.app_env}


@app.get('/readiness')
def readiness():
    db = SessionLocal()
    try:
        db.execute(text('SELECT 1'))
        db.commit()
        return {'status': 'ready', 'database': 'ok'}
    finally:
        db.close()


@app.get('/metrics')
def metrics():
    return {
        'app_name': settings.app_name,
        'env': settings.app_env,
        'timezone': settings.app_timezone,
        'locale': settings.default_locale,
        'currency': settings.default_currency,
    }


app.include_router(api_router)
