# app/core/circuit_breaker.py
import asyncio
import time
import logging
from enum import Enum
from typing import Callable, Any, Optional
from dataclasses import dataclass
from statistics import mean

class CircuitState(Enum):
    """Estados do Circuit Breaker."""
    CLOSED = "closed"        # Funcionamento normal
    OPEN = "open"           # Circuito aberto (falhas detectadas)
    HALF_OPEN = "half_open" # Teste de recuperação

@dataclass
class CircuitBreakerConfig:
    """Configuração do Circuit Breaker."""
    failure_threshold: int = 5          # Falhas para abrir circuito
    recovery_timeout: int = 60          # Segundos para tentar recuperação
    success_threshold: int = 3          # Sucessos para fechar circuito
    timeout: float = 30.0              # Timeout para operações
    expected_exception: type = Exception # Tipo de exceção que conta como falha

class CircuitBreakerStats:
    """Estatísticas do Circuit Breaker."""
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.requests = []
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
    
    def record_success(self):
        """Registra operação bem-sucedida."""
        self._add_request(True)
        self.success_count += 1
    
    def record_failure(self):
        """Registra falha de operação."""
        self._add_request(False)
        self.failure_count += 1
        self.last_failure_time = time.time()
    
    def _add_request(self, success: bool):
        """Adiciona requisição à janela deslizante."""
        if len(self.requests) >= self.window_size:
            # Remove requisição mais antiga
            removed = self.requests.pop(0)
            if removed:
                self.success_count -= 1
            else:
                self.failure_count -= 1
        
        self.requests.append(success)
    
    @property
    def failure_rate(self) -> float:
        """Taxa de falha na janela atual."""
        total = len(self.requests)
        if total == 0:
            return 0.0
        return self.failure_count / total
    
    @property
    def total_requests(self) -> int:
        """Total de requisições na janela."""
        return len(self.requests)

class CircuitBreaker:
    """
    Circuit Breaker para proteção contra falhas em cascata.
    
    FUNCIONAMENTO:
    1. CLOSED: Requisições passam normalmente
    2. OPEN: Requisições falham imediatamente
    3. HALF_OPEN: Testa recuperação com requisições limitadas
    
    BENEFÍCIOS:
    - Evita sobrecarga em serviços com falha
    - Recuperação automática
    - Métricas detalhadas
    - Fallback configurável
    """
    
    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig,
        fallback: Optional[Callable] = None
    ):
        self.name = name
        self.config = config
        self.fallback = fallback
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self.last_state_change = time.time()
        self.half_open_success_count = 0
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        EXECUÇÃO PROTEGIDA: Executa função com proteção do circuit breaker.
        
        FLUXO:
        1. Verifica estado do circuito
        2. Executa função se permitido
        3. Atualiza estatísticas
        4. Transiciona estado se necessário
        """
        async with self._lock:
            await self._check_state_transition()
            
            # CIRCUITO ABERTO: Falha imediata
            if self.state == CircuitState.OPEN:
                logging.warning(f"Circuit breaker {self.name} is OPEN - request rejected")
                if self.fallback:
                    return await self._execute_fallback(*args, **kwargs)
                raise CircuitBreakerOpenException(f"Circuit breaker {self.name} is open")
            
            # EXECUÇÃO DA FUNÇÃO
            try:
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.config.timeout
                )
                
                # SUCESSO: Atualiza estatísticas
                await self._on_success()
                return result
                
            except self.config.expected_exception as e:
                # FALHA ESPERADA: Atualiza estatísticas
                await self._on_failure()
                raise
            
            except asyncio.TimeoutError:
                # TIMEOUT: Tratado como falha
                await self._on_failure()
                raise CircuitBreakerTimeoutException(
                    f"Operation timed out after {self.config.timeout}s"
                )
    
    async def _check_state_transition(self):
        """
        MÁQUINA DE ESTADOS: Gerencia transições entre estados.
        """
        now = time.time()
        
        if self.state == CircuitState.OPEN:
            # TENTATIVA DE RECUPERAÇÃO
            if now - self.last_state_change >= self.config.recovery_timeout:
                logging.info(f"Circuit breaker {self.name}: OPEN -> HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
                self.half_open_success_count = 0
                self.last_state_change = now
        
        elif self.state == CircuitState.CLOSED:
            # VERIFICAÇÃO DE FALHAS
            if (self.stats.failure_count >= self.config.failure_threshold and
                self.stats.total_requests >= self.config.failure_threshold):
                
                logging.warning(
                    f"Circuit breaker {self.name}: CLOSED -> OPEN "
                    f"(failure rate: {self.stats.failure_rate:.2%})"
                )
                self.state = CircuitState.OPEN
                self.last_state_change = now
    
    async def _on_success(self):
        """TRATAMENTO DE SUCESSO: Atualiza estado e estatísticas."""
        self.stats.record_success()
        
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_success_count += 1
            
            # RECUPERAÇÃO COMPLETA
            if self.half_open_success_count >= self.config.success_threshold:
                logging.info(f"Circuit breaker {self.name}: HALF_OPEN -> CLOSED")
                self.state = CircuitState.CLOSED
                self.last_state_change = time.time()
                self.half_open_success_count = 0
    
    async def _on_failure(self):
        """TRATAMENTO DE FALHA: Atualiza estado e estatísticas."""
        self.stats.record_failure()
        
        if self.state == CircuitState.HALF_OPEN:
            # FALHA DURANTE TESTE: Volta para OPEN
            logging.warning(f"Circuit breaker {self.name}: HALF_OPEN -> OPEN")
            self.state = CircuitState.OPEN
            self.last_state_change = time.time()
            self.half_open_success_count = 0
    
    async def _execute_fallback(self, *args, **kwargs) -> Any:
        """EXECUÇÃO DE FALLBACK: Função alternativa quando circuito aberto."""
        try:
            if asyncio.iscoroutinefunction(self.fallback):
                return await self.fallback(*args, **kwargs)
            else:
                return self.fallback(*args, **kwargs)
        except Exception as e:
            logging.error(f"Fallback failed for {self.name}: {e}")
            raise
    
    def get_stats(self) -> dict:
        """MÉTRICAS: Retorna estatísticas atuais do circuit breaker."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_rate": self.stats.failure_rate,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "total_requests": self.stats.total_requests,
            "last_state_change": self.last_state_change,
            "last_failure_time": self.stats.last_failure_time
        }

# EXCEÇÕES CUSTOMIZADAS
class CircuitBreakerException(Exception):
    """Exceção base para circuit breaker."""
    pass

class CircuitBreakerOpenException(CircuitBreakerException):
    """Exceção quando circuito está aberto."""
    pass

class CircuitBreakerTimeoutException(CircuitBreakerException):
    """Exceção de timeout."""
    pass

# IMPLEMENTAÇÃO PRÁTICA COM APIs EXTERNAS
class ResilientBookEnrichmentService:
    """
    Serviço de enriquecimento com circuit breakers para cada API externa.
    
    ESTRATÉGIA:
    - Circuit breaker separado para cada API
    - Fallbacks diferentes por API
    - Métricas agregadas
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # CIRCUIT BREAKERS POR API
        self.google_books_cb = CircuitBreaker(
            name="google_books",
            config=CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=30,
                timeout=10.0,
                expected_exception=(httpx.HTTPError, httpx.TimeoutException)
            ),
            fallback=self._google_books_fallback
        )
        
        self.openlibrary_cb = CircuitBreaker(
            name="openlibrary",
            config=CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=60,
                timeout=15.0,
                expected_exception=(httpx.HTTPError, httpx.TimeoutException)
            ),
            fallback=self._openlibrary_fallback
        )
    
    async def enrich_book_data(self, title: str, isbn: str = None) -> dict:
        """
        ENRIQUECIMENTO RESILIENTE: Usa circuit breakers para cada API.
        
        ESTRATÉGIA:
        - Executa APIs em paralelo com proteção
        - Combina resultados disponíveis
        - Falha gracefully se todas as APIs estiverem indisponíveis
        """
        tasks = []
        
        # GOOGLE BOOKS COM CIRCUIT BREAKER
        if isbn:
            tasks.append(
                self.google_books_cb.call(self._fetch_google_books, isbn)
            )
        
        # OPENLIBRARY COM CIRCUIT BREAKER
        if isbn:
            tasks.append(
                self.openlibrary_cb.call(self._fetch_openlibrary, isbn)
            )
        
        # EXECUÇÃO PARALELA COM TRATAMENTO DE ERROS
        results = []
        for task in tasks:
            try:
                result = await task
                if result:
                    results.append(result)
            except CircuitBreakerOpenException:
                logging.warning("Circuit breaker open - skipping API call")
            except Exception as e:
                logging.error(f"API call failed: {e}")
        
        # CONSOLIDAÇÃO DE RESULTADOS
        consolidated = {}
        for result in results:
            consolidated.update(result)
        
        return consolidated
    
    async def _fetch_google_books(self, isbn: str) -> dict:
        """Busca dados na API Google Books."""
        url = f"https://www.googleapis.com/books/v1/volumes"
        params = {"q": f"isbn:{isbn}"}
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        if data.get("totalItems", 0) > 0:
            book_info = data["items"][0]["volumeInfo"]
            return {
                "title": book_info.get("title"),
                "authors": book_info.get("authors", []),
                "description": book_info.get("description"),
                "cover_url": book_info.get("imageLinks", {}).get("thumbnail"),
                "page_count": book_info.get("pageCount"),
                "publisher": book_info.get("publisher"),
                "published_date": book_info.get("publishedDate"),
                "source": "google_books"
            }
        
        return {}
    
    async def _fetch_openlibrary(self, isbn: str) -> dict:
        """Busca dados na API OpenLibrary."""
        url = f"https://openlibrary.org/api/books"
        params = {
            "bibkeys": f"ISBN:{isbn}",
            "jscmd": "data",
            "format": "json"
        }
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        isbn_key = f"ISBN:{isbn}"
        
        if isbn_key in data:
            book_info = data[isbn_key]
            return {
                "title": book_info.get("title"),
                "authors": [author["name"] for author in book_info.get("authors", [])],
                "publisher": book_info.get("publishers", [{}])[0].get("name"),
                "publish_date": book_info.get("publish_date"),
                "subjects": book_info.get("subjects", []),
                "source": "openlibrary"
            }
        
        return {}
    
    async def _google_books_fallback(self, isbn: str) -> dict:
        """Fallback para Google Books API."""
        return {
            "title": f"Livro ISBN {isbn}",
            "description": "Informações não disponíveis temporariamente",
            "source": "fallback_google"
        }
    
    async def _openlibrary_fallback(self, isbn: str) -> dict:
        """Fallback para OpenLibrary API."""
        return {
            "subjects": ["Literatura"],
            "source": "fallback_openlibrary"
        }
    
    def get_circuit_breaker_stats(self) -> dict:
        """MÉTRICAS: Estatísticas de todos os circuit breakers."""
        return {
            "google_books": self.google_books_cb.get_stats(),
            "openlibrary": self.openlibrary_cb.get_stats()
        }

# ENDPOINT PARA MONITORAMENTO
@app.get("/health/circuit-breakers")
async def circuit_breaker_health(
    enrichment_service: ResilientBookEnrichmentService = Depends()
):
    """
    HEALTH CHECK: Estado dos circuit breakers.
    
    USO: Monitoramento e alertas
    """
    stats = enrichment_service.get_circuit_breaker_stats()
    
    # CÁLCULO DE STATUS GERAL
    all_healthy = all(
        cb["state"] == "closed" 
        for cb in stats.values()
    )
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "circuit_breakers": stats,
        "timestamp": time.time()
    }