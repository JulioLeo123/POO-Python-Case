# app/core/exceptions.py
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
import logging
from typing import Dict, Any

class BibliotecaAPIException(Exception):
    """
    EXCEÇÃO BASE: Exceção customizada para erros de negócio.
    
    CONCEITO: Hierarquia de exceções permite tratamento
    específico para diferentes tipos de erro.
    """
    def __init__(self, message: str, status_code: int = 500, details: Dict[str, Any] = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class AuthorNotFoundError(BibliotecaAPIException):
    """Exceção para autor não encontrado."""
    def __init__(self, author_id: int):
        super().__init__(
            message=f"Autor com ID {author_id} não foi encontrado",
            status_code=404,
            details={"author_id": author_id}
        )

class BookNotFoundError(BibliotecaAPIException):
    """Exceção para livro não encontrado."""
    def __init__(self, book_id: int):
        super().__init__(
            message=f"Livro com ID {book_id} não foi encontrado",
            status_code=404,
            details={"book_id": book_id}
        )

class ExternalAPIError(BibliotecaAPIException):
    """Exceção para falhas em APIs externas."""
    def __init__(self, api_name: str, details: str):
        super().__init__(
            message=f"Falha na API externa {api_name}: {details}",
            status_code=503,
            details={"api_name": api_name, "error_details": details}
        )

# Exception Handlers
async def biblioteca_exception_handler(request: Request, exc: BibliotecaAPIException):
    """
    HANDLER CUSTOMIZADO: Trata exceções específicas da aplicação.
    
    PADRONIZAÇÃO: Garante formato consistente de erro
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "details": exc.details,
            "path": str(request.url),
            "request_id": getattr(request.state, 'request_id', None)
        }
    )

async def validation_exception_handler(request: Request, exc: ValidationError):
    """
    HANDLER PYDANTIC: Formata erros de validação de forma amigável.
    """
    return JSONResponse(
        status_code=422,
        content={
            "error": "Dados inválidos fornecidos",
            "details": [
                {
                    "field": ".".join(str(loc) for loc in error["loc"]),
                    "message": error["msg"],
                    "type": error["type"]
                }
                for error in exc.errors()
            ],
            "path": str(request.url)
        }
    )

async def http_exception_handler(request: Request, exc: HTTPException):
    """
    HANDLER HTTP: Padroniza respostas HTTPException.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url)
        }
    )

async def general_exception_handler(request: Request, exc: Exception):
    """
    HANDLER GENÉRICO: Captura erros não tratados.
    
    SEGURANÇA: Não expõe detalhes internos em produção
    """
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Erro interno do servidor",
            "message": "Algo deu errado. Nossa equipe foi notificada.",
            "path": str(request.url)
        }
    )