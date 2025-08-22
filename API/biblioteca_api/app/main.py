# app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import time
import uuid
import logging
from contextlib import asynccontextmanager
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from .core.config import settings
from .core.exceptions import (
    BibliotecaAPIException, biblioteca_exception_handler,
    validation_exception_handler, http_exception_handler,
    general_exception_handler
)
from .routers import books, authors
from .services.cache import CacheService
from .services.external_apis import BookEnrichmentService
from pydantic import ValidationError
from fastapi import HTTPException

# Métricas Prometheus
REQUEST_COUNT = Counter('fastapi_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('fastapi_request_duration_seconds', 'Request duration')

# CONFIGURAÇÃO DE LOGGING
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    LIFECYCLE MANAGEMENT: Gerencia inicialização e limpeza.
    
    CONCEITO: Context manager para recursos que precisam
    ser inicializados/finalizados adequadamente.
    """
    # INICIALIZAÇÃO
    logging.info("Iniciando Biblioteca API...")
    
    # Aqui seria inicialização de DB, conexões, etc.
    # cache_service = CacheService(settings.redis_url)
    
    yield  # Aplicação roda aqui
    
    # LIMPEZA
    logging.info("Finalizando Biblioteca API...")
    # await cache_service.close()

# CRIAÇÃO DA APLICAÇÃO
app = FastAPI(
    title=settings.app_name,
    description="API RESTful para gerenciamento de biblioteca digital",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# MIDDLEWARES
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Em produção, especificar hosts
)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """
    MIDDLEWARE PARA MÉTRICAS: Coleta dados para Prometheus.
    """
    start_time = time.time()
    
    response = await call_next(request)
    
    # Registrar métricas
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    REQUEST_DURATION.observe(time.time() - start_time)
    
    return response

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    MIDDLEWARE CUSTOMIZADO: Logging e timing de requisições.
    
    OBSERVABILIDADE: Coleta métricas para monitoramento
    """
    # GERAÇÃO DE REQUEST ID
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # INÍCIO DO TIMING
    start_time = time.time()
    
    # LOG DA REQUISIÇÃO
    logging.info(
        f"Request started: {request.method} {request.url} "
        f"[{request_id}]"
    )
    
    # PROCESSAMENTO DA REQUISIÇÃO
    response = await call_next(request)
    
    # CÁLCULO DE TEMPO DE PROCESSAMENTO
    process_time = time.time() - start_time
    
    # LOG DA RESPOSTA
    logging.info(
        f"Request completed: {request.method} {request.url} "
        f"[{request_id}] - {response.status_code} - {process_time:.3f}s"
    )
    
    # ADIÇÃO DE HEADERS
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(process_time)
    
    return response

# EXCEPTION HANDLERS
app.add_exception_handler(BibliotecaAPIException, biblioteca_exception_handler)
app.add_exception_handler(ValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# ROUTERS
app.include_router(books.router, prefix="/api/v1")
app.include_router(authors.router, prefix="/api/v1")

# HEALTH CHECK
@app.get("/health", tags=["health"])
async def health_check():
    """
    HEALTH CHECK: Endpoint para verificação de saúde.
    
    USO: Load balancers e monitoramento
    """
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "timestamp": time.time()
    }

# MÉTRICAS PROMETHEUS
@app.get("/metrics", tags=["monitoring"])
async def metrics():
    """Endpoint para métricas do Prometheus."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# ROOT ENDPOINT
@app.get("/", tags=["root"])
async def root():
    """
    ENDPOINT RAIZ: Informações básicas da API.
    """
    return {
        "message": f"Bem-vindo à {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",
        "redoc": "/redoc"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )