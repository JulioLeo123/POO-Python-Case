# app/services/external_apis.py
import httpx
import asyncio
import logging
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class BookEnrichmentService:
    """
    Serviço para enriquecer dados de livros usando APIs externas.
    
    CONCEITO: Separation of Concerns - isola lógica de integração
    externa da lógica de negócio principal.
    """
    
    def __init__(self):
        """
        CONFIGURAÇÃO: Inicializa cliente HTTP com configurações
        otimizadas para consumo de APIs externas.
        """
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=5.0,  # Tempo para estabelecer conexão
                read=30.0,    # Tempo para ler resposta
                total=35.0    # Tempo total máximo
            ),
            limits=httpx.Limits(
                max_connections=50,        # Pool de conexões
                max_keepalive_connections=20  # Conexões keep-alive
            ),
            headers={
                "User-Agent": "BibliotecaAPI/1.0 (Educational Purpose)",
                "Accept": "application/json"
            }
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))
    )
    async def _safe_request(
        self, 
        method: str, 
        url: str, 
        **kwargs
    ) -> Optional[httpx.Response]:
        """
        PADRÃO RETRY: Executa requisições com retry automático.
        
        ESTRATÉGIA:
        - Retry apenas em erros de rede/timeout
        - Backoff exponencial para não sobrecarregar
        - Máximo 3 tentativas
        """
        try:
            response = await self.client.request(method, url, **kwargs)
            
            # TRATAMENTO DE STATUS: Lança exceção para 5xx
            if response.status_code >= 500:
                response.raise_for_status()
            
            return response
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                # Re-raise para trigger retry
                raise
            else:
                # 4xx errors não devem fazer retry
                logging.warning(f"Client error {e.response.status_code}: {e}")
                return e.response
                
        except Exception as e:
            logging.error(f"Request failed: {e}")
            raise
    
    async def enrich_book_data(
        self, 
        title: str, 
        isbn: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        ENRIQUECIMENTO PRINCIPAL: Combina dados de múltiplas APIs.
        
        ESTRATÉGIA:
        - Tenta múltiplas fontes em paralelo
        - Combina resultados de forma inteligente
        - Falha gracefully se APIs estiverem indisponíveis
        """
        
        # EXECUÇÃO PARALELA: Múltiplas APIs simultaneamente
        tasks = []
        
        if isbn:
            tasks.append(self._get_google_books_data(isbn))
            tasks.append(self._get_openlibrary_data(isbn))
        
        tasks.append(self._get_goodreads_data(title))
        
        # AGUARDA TODAS AS RESPOSTAS (com timeout)
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logging.warning("Timeout ao buscar dados externos")
            return {}
        
        # CONSOLIDAÇÃO DE DADOS: Combina resultados
        enriched_data = {}
        
        for result in results:
            if isinstance(result, dict):
                # ESTRATÉGIA DE MERGE: Prioriza dados mais completos
                for key, value in result.items():
                    if value and (key not in enriched_data or not enriched_data[key]):
                        enriched_data[key] = value
        
        return enriched_data
    
    async def _get_google_books_data(self, isbn: str) -> Dict[str, Any]:
        """
        INTEGRAÇÃO GOOGLE BOOKS API: Busca dados bibliográficos.
        
        DOCUMENTAÇÃO: https://developers.google.com/books/docs/v1/using
        """
        try:
            url = f"https://www.googleapis.com/books/v1/volumes"
            params = {
                "q": f"isbn:{isbn}",
                "maxResults": 1
            }
            
            response = await self._safe_request("GET", url, params=params)
            
            if not response or response.status_code != 200:
                return {}
            
            data = response.json()
            
            if not data.get("items"):
                return {}
            
            # EXTRAÇÃO DE DADOS: Parse da resposta da API
            book_info = data["items"][0]["volumeInfo"]
            
            return {
                "summary": book_info.get("description"),
                "cover_url": book_info.get("imageLinks", {}).get("thumbnail"),
                "page_count": book_info.get("pageCount"),
                "categories": book_info.get("categories", []),
                "published_date": book_info.get("publishedDate"),
                "language": book_info.get("language")
            }
            
        except Exception as e:
            logging.error(f"Erro na API Google Books: {e}")
            return {}
    
    async def _get_openlibrary_data(self, isbn: str) -> Dict[str, Any]:
        """
        INTEGRAÇÃO OPENLIBRARY API: Dados bibliográficos alternativos.
        
        DOCUMENTAÇÃO: https://openlibrary.org/developers/api
        """
        try:
            url = f"https://openlibrary.org/api/books"
            params = {
                "bibkeys": f"ISBN:{isbn}",
                "jscmd": "data",
                "format": "json"
            }
            
            response = await self._safe_request("GET", url, params=params)
            
            if not response or response.status_code != 200:
                return {}
            
            data = response.json()
            book_key = f"ISBN:{isbn}"
            
            if book_key not in data:
                return {}
            
            book_info = data[book_key]
            
            # MAPEAMENTO DE DADOS: Adapta formato da API
            return {
                "summary": book_info.get("excerpts", [{}])[0].get("text"),
                "cover_url": book_info.get("cover", {}).get("medium"),
                "subjects": [s["name"] for s in book_info.get("subjects", [])],
                "publish_date": book_info.get("publish_date")
            }
            
        except Exception as e:
            logging.error(f"Erro na API OpenLibrary: {e}")
            return {}
    
    async def _get_goodreads_data(self, title: str) -> Dict[str, Any]:
        """
        SIMULAÇÃO GOODREADS: API real requer autenticação complexa.
        
        CONCEITO: Demonstra como lidar com APIs que têm
        requisitos de autenticação mais rigorosos.
        """
        try:
            # Em produção, usar API key e OAuth
            # Por ora, simula resposta baseada no título
            
            # SIMULAÇÃO REALISTA: Dados baseados em padrões reais
            simulated_rating = hash(title) % 50 / 10 + 3.0  # Rating 3.0-8.0
            
            return {
                "rating": round(simulated_rating, 1),
                "reviews_count": abs(hash(title)) % 10000,
                "popularity_score": abs(hash(title)) % 100
            }
            
        except Exception as e:
            logging.error(f"Erro simulando dados Goodreads: {e}")
            return {}
    
    async def close(self):
        """LIMPEZA: Fecha cliente HTTP adequadamente."""
        await self.client.aclose()