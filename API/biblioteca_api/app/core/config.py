# app/core/config.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    """
    CONFIGURAÇÃO CENTRALIZADA: Usa Pydantic para validação
    e carregamento de variáveis de ambiente.
    
    PADRÃO 12-FACTOR APP: Configuração via ambiente
    """
    
    # Configurações da aplicação
    app_name: str = Field(default="Biblioteca API", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Configurações de API externa
    google_books_api_key: Optional[str] = Field(None, env="GOOGLE_BOOKS_API_KEY")
    request_timeout: int = Field(default=30, env="REQUEST_TIMEOUT")
    
    # Configurações de cache
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    cache_ttl: int = Field(default=300, env="CACHE_TTL")
    
    # Configurações de logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Instância global de configurações
settings = Settings()