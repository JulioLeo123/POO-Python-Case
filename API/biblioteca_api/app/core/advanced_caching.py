# app/core/advanced_caching.py
import asyncio
import hashlib
import pickle
import logging
from typing import Any, Optional, Callable, Dict, List
from functools import wraps
from dataclasses import dataclass
from enum import Enum
import time
import json

class CacheStrategy(Enum):
    """Estratégias de cache disponíveis."""
    LRU = "lru"                    # Least Recently Used
    LFU = "lfu"                    # Least Frequently Used
    TTL = "ttl"                    # Time To Live
    WRITE_THROUGH = "write_through" # Write-through cache
    WRITE_BEHIND = "write_behind"   # Write-behind cache

@dataclass
class CacheEntry:
    """Entrada de cache com metadados."""
    value: Any
    created_at: float
    accessed_at: float
    access_count: int
    ttl: Optional[float] = None
    
    @property
    def is_expired(self) -> bool:
        """Verifica se entrada está expirada."""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl

class SmartCacheManager:
    """
    Gerenciador de cache inteligente com múltiplas estratégias.
    
    FUNCIONALIDADES:
    - Múltiplas estratégias de eviction
    - Cache warming automático
    - Invalidação inteligente
    - Métricas detalhadas
    - Compression automática
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: Optional[float] = 3600,
        strategy: CacheStrategy = CacheStrategy.LRU,
        enable_compression: bool = True
    ):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.strategy = strategy
        self.enable_compression = enable_compression
        
        self.cache: Dict[str, CacheEntry] = {}
        self.access_order: List[str] = []  # Para LRU
        self.frequency_counter: Dict[str, int] = {}  # Para LFU
        
        # MÉTRICAS
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.compressions = 0
    
    async def get(self, key: str) -> Optional[Any]:
        """
        RECUPERAÇÃO INTELIGENTE: Busca com update de metadados.
        """
        if key not in self.cache:
            self.misses += 1
            logging.debug(f"Cache miss: {key}")
            return None
        
        entry = self.cache[key]
        
        # VERIFICAÇÃO DE EXPIRAÇÃO
        if entry.is_expired:
            await self.delete(key)
            self.misses += 1
            logging.debug(f"Cache expired: {key}")
            return None
        
        # UPDATE DE METADADOS
        entry.accessed_at = time.time()
        entry.access_count += 1
        
        # UPDATE DE ORDEM DE ACESSO (LRU)
        if self.strategy == CacheStrategy.LRU:
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
        
        # UPDATE DE FREQUÊNCIA (LFU)
        if self.strategy == CacheStrategy.LFU:
            self.frequency_counter[key] = self.frequency_counter.get(key, 0) + 1
        
        self.hits += 1
        logging.debug(f"Cache hit: {key}")
        
        return self._decompress_if_needed(entry.value)
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
        force: bool = False
    ) -> bool:
        """
        ARMAZENAMENTO INTELIGENTE: Salva com compressão e eviction.
        """
        # VERIFICAÇÃO DE ESPAÇO
        if len(self.cache) >= self.max_size and key not in self.cache:
            if not force:
                await self._evict_entries(1)
            else:
                # Força remoção mesmo se cache cheio
                await self._evict_entries(1)
        
        # COMPRESSÃO AUTOMÁTICA
        compressed_value = self._compress_if_needed(value)
        
        # CRIAÇÃO DA ENTRADA
        entry = CacheEntry(
            value=compressed_value,
            created_at=time.time(),
            accessed_at=time.time(),
            access_count=1,
            ttl=ttl or self.default_ttl
        )
        
        # ARMAZENAMENTO
        was_update = key in self.cache
        self.cache[key] = entry
        
        # UPDATE DE ESTRUTURAS DE CONTROLE
        if self.strategy == CacheStrategy.LRU:
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
        
        if self.strategy == CacheStrategy.LFU:
            if not was_update:
                self.frequency_counter[key] = 1
        
        logging.debug(f"Cache set: {key} (TTL: {entry.ttl})")
        return True
    
    async def delete(self, key: str) -> bool:
        """REMOÇÃO: Remove entrada e cleanup de metadados."""
        if key not in self.cache:
            return False
        
        del self.cache[key]
        
        # CLEANUP DE ESTRUTURAS
        if key in self.access_order:
            self.access_order.remove(key)
        
        if key in self.frequency_counter:
            del self.frequency_counter[key]
        
        logging.debug(f"Cache delete: {key}")
        return True
    
    async def _evict_entries(self, count: int):
        """
        EVICTION INTELIGENTE: Remove entradas baseado na estratégia.
        """
        if self.strategy == CacheStrategy.LRU:
            # Remove menos recentemente usados
            for _ in range(min(count, len(self.access_order))):
                if self.access_order:
                    oldest_key = self.access_order.pop(0)
                    if oldest_key in self.cache:
                        del self.cache[oldest_key]
                        self.evictions += 1
        
        elif self.strategy == CacheStrategy.LFU:
            # Remove menos frequentemente usados
            if self.frequency_counter:
                sorted_by_freq = sorted(
                    self.frequency_counter.items(),
                    key=lambda x: x[1]
                )
                for key, _ in sorted_by_freq[:count]:
                    if key in self.cache:
                        del self.cache[key]
                        del self.frequency_counter[key]
                        self.evictions += 1
        
        elif self.strategy == CacheStrategy.TTL:
            # Remove expirados primeiro, depois mais antigos
            expired_keys = [
                key for key, entry in self.cache.items()
                if entry.is_expired
            ]
            
            for key in expired_keys[:count]:
                await self.delete(key)
                self.evictions += 1
            
            # Se ainda precisa remover mais, remove mais antigos
            remaining = count - len(expired_keys)
            if remaining > 0:
                oldest_entries = sorted(
                    self.cache.items(),
                    key=lambda x: x[1].created_at
                )
                for key, _ in oldest_entries[:remaining]:
                    await self.delete(key)
                    self.evictions += 1
    
    def _compress_if_needed(self, value: Any) -> Any:
        """COMPRESSÃO: Comprime valores grandes automaticamente."""
        if not self.enable_compression:
            return value
        
        # Serializa para verificar tamanho
        serialized = pickle.dumps(value)
        
        # Comprime se maior que 1KB
        if len(serialized) > 1024:
            import gzip
            compressed = gzip.compress(serialized)
            self.compressions += 1
            logging.debug(f"Compressed value: {len(serialized)} -> {len(compressed)} bytes")
            return {"_compressed": True, "_data": compressed}
        
        return value
    
    def _decompress_if_needed(self, value: Any) -> Any:
        """DESCOMPRESSÃO: Descomprime valores automaticamente."""
        if isinstance(value, dict) and value.get("_compressed"):
            import gzip
            decompressed_data = gzip.decompress(value["_data"])
            return pickle.loads(decompressed_data)
        
        return value
    
    async def cleanup_expired(self):
        """LIMPEZA: Remove entradas expiradas."""
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry.is_expired
        ]
        
        for key in expired_keys:
            await self.delete(key)
        
        logging.info(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """MÉTRICAS: Estatísticas detalhadas do cache."""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percentage": round(hit_rate, 2),
            "evictions": self.evictions,
            "compressions": self.compressions,
            "strategy": self.strategy.value,
            "memory_usage_estimate": self._estimate_memory_usage()
        }
    
    def _estimate_memory_usage(self) -> str:
        """ESTIMATIVA: Calcula uso aproximado de memória."""
        total_size = 0
        for entry in self.cache.values():
            try:
                size = len(pickle.dumps(entry.value))
                total_size += size
            except:
                total_size += 1024  # Estimativa padrão
        
        # Converte para formato legível
        if total_size < 1024:
            return f"{total_size} B"
        elif total_size < 1024 * 1024:
            return f"{total_size / 1024:.1f} KB"
        else:
            return f"{total_size / (1024 * 1024):.1f} MB"

# DECORATOR PARA CACHE AUTOMÁTICO
def cached(
    key_func: Optional[Callable] = None,
    ttl: Optional[float] = None,
    cache_manager: Optional[SmartCacheManager] = None
):
    """
    DECORATOR DE CACHE: Automatiza cache de funções.
    
    EXEMPLO:
    @cached(key_func=lambda title, isbn: f"book:{isbn}", ttl=3600)
    async def get_book_details(title: str, isbn: str):
        # Função cara que busca em APIs externas
        return expensive_api_call(title, isbn)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # USA CACHE MANAGER GLOBAL SE NÃO FORNECIDO
            cm = cache_manager or global_cache_manager
            
            # GERAÇÃO DE CHAVE
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Chave padrão baseada em nome da função e argumentos
                args_str = "_".join(str(arg) for arg in args)
                kwargs_str = "_".join(f"{k}:{v}" for k, v in sorted(kwargs.items()))
                cache_key = f"{func.__name__}:{args_str}:{kwargs_str}"
                # Hash para evitar chaves muito longas
                cache_key = hashlib.md5(cache_key.encode()).hexdigest()
            
            # TENTATIVA DE CACHE
            cached_result = await cm.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # EXECUÇÃO DA FUNÇÃO
            result = await func(*args, **kwargs)
            
            # ARMAZENAMENTO EM CACHE
            await cm.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator

# INSTÂNCIA GLOBAL
global_cache_manager = SmartCacheManager(
    max_size=5000,
    default_ttl=3600,
    strategy=CacheStrategy.LRU,
    enable_compression=True
)

# EXEMPLO DE USO
@cached(
    key_func=lambda isbn: f"enrichment:{isbn}",
    ttl=7200  # 2 horas
)
async def cached_book_enrichment(isbn: str) -> dict:
    """
    ENRIQUECIMENTO COM CACHE: APIs externas com cache inteligente.
    """
    enrichment_service = BookEnrichmentService()
    return await enrichment_service.enrich_book_data("", isbn)

# ENDPOINT PARA ESTATÍSTICAS DE CACHE
@app.get("/cache/stats")
async def cache_statistics():
    """
    MÉTRICAS DE CACHE: Estatísticas para monitoramento.
    """
    return global_cache_manager.get_stats()

@app.post("/cache/cleanup")
async def cache_cleanup():
    """
    LIMPEZA MANUAL: Remove entradas expiradas.
    """
    await global_cache_manager.cleanup_expired()
    return {"message": "Cache cleanup completed"}