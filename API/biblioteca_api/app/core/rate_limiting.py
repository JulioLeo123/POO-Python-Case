# app/core/rate_limiting.py
import time
import asyncio
from typing import Dict, Optional
from fastapi import HTTPException, status, Depends, Request
from collections import defaultdict, deque
import redis.asyncio as redis

class RateLimiter:
    """
    Rate Limiter avançado com múltiplas estratégias.
    
    ALGORITMOS IMPLEMENTADOS:
    - Token Bucket: Para rajadas controladas
    - Sliding Window: Para distribuição uniforme
    - Fixed Window: Para simplicidade
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        CONFIGURAÇÃO: Permite rate limiting distribuído via Redis.
        
        FALLBACK: Se Redis não disponível, usa memória local
        """
        self.redis_client = redis_client
        self.local_windows: Dict[str, deque] = defaultdict(deque)
        self.local_buckets: Dict[str, dict] = defaultdict(dict)
    
    async def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        algorithm: str = "sliding_window"
    ) -> tuple[bool, dict]:
        """
        VERIFICAÇÃO DE RATE LIMIT: Determina se requisição é permitida.
        
        RETORNO:
        - bool: True se permitida
        - dict: Metadados (remaining, reset_time, etc.)
        """
        if algorithm == "sliding_window":
            return await self._sliding_window_check(key, max_requests, window_seconds)
        elif algorithm == "token_bucket":
            return await self._token_bucket_check(key, max_requests, window_seconds)
        elif algorithm == "fixed_window":
            return await self._fixed_window_check(key, max_requests, window_seconds)
        else:
            raise ValueError(f"Algoritmo não suportado: {algorithm}")
    
    async def _sliding_window_check(
        self, 
        key: str, 
        max_requests: int, 
        window_seconds: int
    ) -> tuple[bool, dict]:
        """
        SLIDING WINDOW: Janela deslizante para distribuição uniforme.
        
        FUNCIONAMENTO:
        - Mantém timestamps das últimas requisições
        - Remove requisições fora da janela
        - Permite se não exceder limite
        """
        now = time.time()
        window_start = now - window_seconds
        
        if self.redis_client:
            # IMPLEMENTAÇÃO DISTRIBUÍDA COM REDIS
            pipe = self.redis_client.pipeline()
            
            # Remove requisições antigas
            pipe.zremrangebyscore(f"rate_limit:{key}", 0, window_start)
            
            # Conta requisições na janela atual
            pipe.zcard(f"rate_limit:{key}")
            
            # Adiciona requisição atual
            pipe.zadd(f"rate_limit:{key}", {str(now): now})
            
            # Define expiração da chave
            pipe.expire(f"rate_limit:{key}", window_seconds + 1)
            
            results = await pipe.execute()
            current_requests = results[1]
            
        else:
            # IMPLEMENTAÇÃO LOCAL (DESENVOLVIMENTO)
            requests_window = self.local_windows[key]
            
            # Remove requisições antigas
            while requests_window and requests_window[0] < window_start:
                requests_window.popleft()
            
            current_requests = len(requests_window)
            
            if current_requests < max_requests:
                requests_window.append(now)
        
        # CÁLCULO DE METADADOS
        remaining = max(0, max_requests - current_requests - 1)
        reset_time = now + window_seconds
        
        is_allowed = current_requests < max_requests
        
        metadata = {
            "limit": max_requests,
            "remaining": remaining,
            "reset": int(reset_time),
            "retry_after": None if is_allowed else window_seconds
        }
        
        return is_allowed, metadata
    
    async def _token_bucket_check(
        self,
        key: str,
        max_tokens: int,
        refill_rate_per_second: float
    ) -> tuple[bool, dict]:
        """
        TOKEN BUCKET: Permite rajadas até o limite do bucket.
        
        CONCEITO:
        - Bucket tem capacidade máxima de tokens
        - Tokens são adicionados continuamente
        - Cada requisição consome 1 token
        - Permite rajadas se bucket tem tokens
        """
        now = time.time()
        
        if self.redis_client:
            # IMPLEMENTAÇÃO REDIS COM LUA SCRIPT para atomicidade
            lua_script = """
            local key = KEYS[1]
            local max_tokens = tonumber(ARGV[1])
            local refill_rate = tonumber(ARGV[2])
            local now = tonumber(ARGV[3])
            
            local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
            local tokens = tonumber(bucket[1]) or max_tokens
            local last_refill = tonumber(bucket[2]) or now
            
            -- Calcula tokens a adicionar
            local time_passed = now - last_refill
            local tokens_to_add = math.floor(time_passed * refill_rate)
            tokens = math.min(max_tokens, tokens + tokens_to_add)
            
            local allowed = tokens > 0
            if allowed then
                tokens = tokens - 1
            end
            
            -- Atualiza bucket
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
            redis.call('EXPIRE', key, 3600)  -- 1 hora
            
            return {allowed and 1 or 0, tokens}
            """
            
            result = await self.redis_client.eval(
                lua_script,
                1,
                f"bucket:{key}",
                max_tokens,
                refill_rate_per_second,
                now
            )
            
            is_allowed = bool(result[0])
            remaining_tokens = result[1]
            
        else:
            # IMPLEMENTAÇÃO LOCAL
            bucket = self.local_buckets[key]
            
            if "tokens" not in bucket:
                bucket["tokens"] = max_tokens
                bucket["last_refill"] = now
            
            # REFILL DE TOKENS
            time_passed = now - bucket["last_refill"]
            tokens_to_add = time_passed * refill_rate_per_second
            bucket["tokens"] = min(max_tokens, bucket["tokens"] + tokens_to_add)
            bucket["last_refill"] = now
            
            # CONSUMO DE TOKEN
            is_allowed = bucket["tokens"] >= 1
            if is_allowed:
                bucket["tokens"] -= 1
            
            remaining_tokens = int(bucket["tokens"])
        
        # METADADOS
        metadata = {
            "limit": max_tokens,
            "remaining": remaining_tokens,
            "reset": None,  # Token bucket não tem reset fixo
            "retry_after": None if is_allowed else 1 / refill_rate_per_second
        }
        
        return is_allowed, metadata

# DEPENDENCY PARA RATE LIMITING
def create_rate_limiter(
    max_requests: int,
    window_seconds: int,
    algorithm: str = "sliding_window",
    key_func: Optional[callable] = None
):
    """
    FACTORY: Cria dependency de rate limiting customizado.
    
    EXEMPLO:
    @app.get("/api/books")
    async def get_books(
        request: Request,
        _: dict = Depends(create_rate_limiter(100, 3600))  # 100/hora
    ):
        ...
    """
    rate_limiter = RateLimiter(redis_client=get_redis_client())
    
    async def rate_limit_dependency(request: Request):
        # IDENTIFICAÇÃO DO CLIENTE
        if key_func:
            client_key = key_func(request)
        else:
            # Padrão: IP + User-Agent
            client_ip = request.client.host
            user_agent = request.headers.get("user-agent", "unknown")
            client_key = f"{client_ip}:{hash(user_agent) % 10000}"
        
        # VERIFICAÇÃO DE LIMITE
        is_allowed, metadata = await rate_limiter.is_allowed(
            client_key,
            max_requests,
            window_seconds,
            algorithm
        )
        
        if not is_allowed:
            # HEADERS DE RATE LIMITING (padrão RFC)
            headers = {
                "X-RateLimit-Limit": str(metadata["limit"]),
                "X-RateLimit-Remaining": str(metadata["remaining"]),
                "X-RateLimit-Reset": str(metadata["reset"]) if metadata["reset"] else "",
                "Retry-After": str(metadata["retry_after"]) if metadata["retry_after"] else ""
            }
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit excedido. Tente novamente mais tarde.",
                headers=headers
            )
        
        # ADICIONA HEADERS INFORMATIVOS
        request.state.rate_limit_metadata = metadata
        
        return metadata
    
    return rate_limit_dependency

# MIDDLEWARE PARA ADICIONAR HEADERS DE RATE LIMIT
@app.middleware("http")
async def rate_limit_headers_middleware(request: Request, call_next):
    """
    MIDDLEWARE: Adiciona headers de rate limiting às respostas.
    """
    response = await call_next(request)
    
    # ADICIONA HEADERS SE METADATA DISPONÍVEL
    if hasattr(request.state, "rate_limit_metadata"):
        metadata = request.state.rate_limit_metadata
        response.headers["X-RateLimit-Limit"] = str(metadata["limit"])
        response.headers["X-RateLimit-Remaining"] = str(metadata["remaining"])
        if metadata["reset"]:
            response.headers["X-RateLimit-Reset"] = str(metadata["reset"])
    
    return response

# EXEMPLO DE USO COM API KEYS
@app.get("/api/public/books")
async def public_books_endpoint(
    request: Request,
    api_key: str = Depends(validate_api_key),
    _: dict = Depends(create_rate_limiter(
        max_requests=1000,  # 1000 requests
        window_seconds=3600,  # por hora
        key_func=lambda req: f"api_key:{req.headers.get('X-API-Key', 'anonymous')}"
    ))
):
    """
    ENDPOINT PÚBLICO: Protegido por API key e rate limiting.
    
    ESTRATÉGIA:
    - Rate limiting por API key (não por IP)
    - Diferentes limites por tier de API key
    - Monitoramento de uso para billing
    """
    return {"books": [], "api_key_tier": api_key["tier"]}