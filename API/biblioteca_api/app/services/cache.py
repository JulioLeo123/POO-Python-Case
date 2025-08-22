# app/services/cache.py
import redis.asyncio as redis
import json
import logging
from typing import Any, Optional, Dict, List
from datetime import timedelta
import pickle

class CacheService:
    """
    Serviço de cache using Redis para otimizar performance.
    
    CONCEITO: Cache Pattern - armazena resultados frequentemente
    acessados para reduzir latência e carga no sistema.
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        """
        CONFIGURAÇÃO REDIS: Inicializa conexão com configurações
        otimizadas para alta disponibilidade.
        """
        self.redis_client = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=False,  # Permitir dados binários
            max_connections=20,
            retry_on_timeout=True
        )
        self.default_ttl = 300  # 5 minutos padrão
    
    async def get(self, key: str) -> Optional[Any]:
        """
        RECUPERAÇÃO DE CACHE: Busca valor por chave.
        
        ESTRATÉGIA:
        - Serialização automática via pickle para objetos complexos
        - Logging para monitoramento de cache hits/misses
        - Tratamento graceful de erros de conexão
        """
        try:
            cached_data = await self.redis_client.get(key)
            
            if cached_data is None:
                logging.debug(f"Cache miss: {key}")
                return None
            
            # DESERIALIZAÇÃO: Converte bytes para objeto Python
            try:
                return pickle.loads(cached_data)
            except pickle.PickleError:
                # Fallback para JSON se pickle falhar
                return json.loads(cached_data.decode('utf-8'))
                
        except redis.ConnectionError:
            logging.warning(f"Redis connection error para chave: {key}")
            return None
        except Exception as e:
            logging.error(f"Erro inesperado no cache: {e}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        expire: Optional[int] = None
    ) -> bool:
        """
        ARMAZENAMENTO EM CACHE: Salva valor com TTL opcional.
        
        CONCEITOS:
        - TTL (Time To Live) para expiração automática
        - Serialização eficiente via pickle
        - Error handling para garantir robustez
        """
        try:
            # SERIALIZAÇÃO: Converte objeto Python para bytes
            if isinstance(value, (str, int, float)):
                serialized_value = str(value).encode('utf-8')
            else:
                serialized_value = pickle.dumps(value)
            
            # CONFIGURAÇÃO DE TTL
            ttl = expire or self.default_ttl
            
            # ARMAZENAMENTO: Set com expiração
            await self.redis_client.setex(key, ttl, serialized_value)
            
            logging.debug(f"Cache set: {key} (TTL: {ttl}s)")
            return True
            
        except redis.ConnectionError:
            logging.warning(f"Redis connection error ao definir: {key}")
            return False
        except Exception as e:
            logging.error(f"Erro ao definir cache: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        INVALIDAÇÃO DE CACHE: Remove chave específica.
        
        USO: Limpar cache quando dados são atualizados
        """
        try:
            result = await self.redis_client.delete(key)
            logging.debug(f"Cache delete: {key} (existed: {bool(result)})")
            return bool(result)
        except Exception as e:
            logging.error(f"Erro ao deletar cache: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        INVALIDAÇÃO POR PADRÃO: Remove múltiplas chaves.
        
        EXEMPLO: delete_pattern("books_list:*") remove todos
        os caches de listagem de livros.
        """
        try:
            # BUSCA POR PADRÃO: Encontra chaves correspondentes
            keys = []
            async for key in self.redis_client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                # DELEÇÃO EM LOTE: Remove todas de uma vez
                deleted_count = await self.redis_client.delete(*keys)
                logging.debug(f"Cache pattern delete: {pattern} ({deleted_count} keys)")
                return deleted_count
            
            return 0
            
        except Exception as e:
            logging.error(f"Erro ao deletar pattern: {e}")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        MONITORAMENTO: Retorna estatísticas do cache.
        
        MÉTRICAS ÚTEIS:
        - Hit ratio para análise de eficiência
        - Uso de memória
        - Número de chaves ativas
        """
        try:
            info = await self.redis_client.info()
            
            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_ratio": self._calculate_hit_ratio(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                )
            }
        except Exception as e:
            logging.error(f"Erro ao obter stats: {e}")
            return {}
    
    def _calculate_hit_ratio(self, hits: int, misses: int) -> float:
        """Calcula taxa de acerto do cache."""
        total = hits + misses
        return (hits / total * 100) if total > 0 else 0.0
    
    async def close(self):
        """LIMPEZA: Fecha conexão Redis."""
        await self.redis_client.close()