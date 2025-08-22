# tests/test_books.py
import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from app.main import app
from app.models.book import BookCreate, BookStatus

# CONFIGURAÇÃO DE TESTE
client = TestClient(app)

class TestBooksAPI:
    """
    TESTES DE INTEGRAÇÃO: Testa endpoints da API de livros.
    
    CONCEITOS TESTADOS:
    - CRUD operations
    - Validação de dados
    - Error handling
    - Cache behavior
    """
    
    def test_create_book_success(self):
        """
        TESTE POSITIVO: Criação bem-sucedida de livro.
        
        CENÁRIO:
        - Dados válidos fornecidos
        - Autor existe
        - API externa retorna dados
        """
        # ARRANGE: Preparar dados de teste
        book_data = {
            "title": "O Alquimista",
            "isbn": "9788573028751",
            "author_id": 1,
            "publication_year": 1988,
            "pages": 163,
            "genre": "Ficção",
            "summary": "A história de Santiago..."
        }
        
        # MOCK: Simular dependências externas
        with patch('app.services.external_apis.BookEnrichmentService') as mock_service:
            mock_service.return_value.enrich_book_data.return_value = {
                "rating": 8.5,
                "cover_url": "http://example.com/cover.jpg"
            }
            
            # ACT: Executar operação
            response = client.post("/api/v1/books/", json=book_data)
        
        # ASSERT: Verificar resultados
        assert response.status_code == 201
        assert response.json()["title"] == book_data["title"]
        assert response.json()["isbn"] == book_data["isbn"]
        assert "id" in response.json()
    
    def test_create_book_invalid_isbn(self):
        """
        TESTE NEGATIVO: ISBN inválido deve retornar erro.
        
        VALIDAÇÃO: Algoritmo de verificação ISBN
        """
        book_data = {
            "title": "Livro Teste",
            "isbn": "1234567890",  # ISBN inválido
            "author_id": 1,
            "publication_year": 2023
        }
        
        response = client.post("/api/v1/books/", json=book_data)
        
        assert response.status_code == 422
        assert "validation" in response.json()["error"].lower()
    
    def test_create_book_missing_required_fields(self):
        """
        TESTE NEGATIVO: Campos obrigatórios ausentes.
        """
        book_data = {
            "title": "Livro Incompleto"
            # author_id ausente (obrigatório)
        }
        
        response = client.post("/api/v1/books/", json=book_data)
        
        assert response.status_code == 422
        assert any("author_id" in error["field"] for error in response.json()["details"])
    
    def test_list_books_with_filters(self):
        """
        TESTE DE FILTROS: Listagem com query parameters.
        """
        # ARRANGE: Criar livros de teste
        self._create_test_books()
        
        # ACT: Buscar com filtros
        response = client.get("/api/v1/books/?genre=ficção&limit=5")
        
        # ASSERT
        assert response.status_code == 200
        books = response.json()
        assert len(books) <= 5
        # Verificar se filtro foi aplicado
        for book in books:
            assert book["genre"].lower() == "ficção"
    
    def test_get_book_not_found(self):
        """
        TESTE NEGATIVO: Buscar livro inexistente.
        """
        response = client.get("/api/v1/books/99999")
        
        assert response.status_code == 404
        assert "não encontrado" in response.json()["error"]
    
    def test_update_book_partial(self):
        """
        TESTE PATCH: Atualização parcial de livro.
        """
        # ARRANGE: Criar livro
        book_id = self._create_test_book()
        
        # ACT: Atualizar apenas título
        update_data = {"title": "Título Atualizado"}
        response = client.patch(f"/api/v1/books/{book_id}", json=update_data)
        
        # ASSERT
        assert response.status_code == 200
        assert response.json()["title"] == "Título Atualizado"
        # Outros campos devem permanecer inalterados
        assert response.json()["author_id"] == 1
    
    def test_delete_borrowed_book_forbidden(self):
        """
        TESTE DE REGRA DE NEGÓCIO: Não pode deletar livro emprestado.
        """
        # ARRANGE: Criar livro emprestado
        book_id = self._create_test_book(status="borrowed")
        
        # ACT: Tentar deletar
        response = client.delete(f"/api/v1/books/{book_id}")
        
        # ASSERT
        assert response.status_code == 400
        assert "emprestado" in response.json()["error"]
    
    @pytest.mark.asyncio
    async def test_external_api_timeout_handling(self):
        """
        TESTE DE RESILÊNCIA: Comportamento com timeout de API externa.
        """
        book_data = {
            "title": "Livro Teste",
            "author_id": 1
        }
        
        # MOCK: Simular timeout
        with patch('app.services.external_apis.BookEnrichmentService') as mock_service:
            mock_service.return_value.enrich_book_data.side_effect = asyncio.TimeoutError()
            
            response = client.post("/api/v1/books/", json=book_data)
        
        # ASSERT: Livro deve ser criado mesmo com falha na API externa
        assert response.status_code == 201
        assert response.json()["external_rating"] is None
    
    def test_cache_behavior(self):
        """
        TESTE DE CACHE: Verificar se cache está funcionando.
        """
        book_id = self._create_test_book()
        
        # Primeira requisição (miss)
        response1 = client.get(f"/api/v1/books/{book_id}")
        
        # Segunda requisição (hit - deve ser mais rápida)
        response2 = client.get(f"/api/v1/books/{book_id}")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json() == response2.json()
    
    # MÉTODOS AUXILIARES
    def _create_test_book(self, status: str = "available") -> int:
        """Cria livro de teste e retorna ID."""
        book_data = {
            "title": "Livro de Teste",
            "author_id": 1,
            "status": status
        }
        response = client.post("/api/v1/books/", json=book_data)
        return response.json()["id"]
    
    def _create_test_books(self) -> List[int]:
        """Cria múltiplos livros de teste."""
        books = [
            {"title": "Ficção 1", "genre": "ficção", "author_id": 1},
            {"title": "Romance 1", "genre": "romance", "author_id": 2},
            {"title": "Ficção 2", "genre": "ficção", "author_id": 1}
        ]
        book_ids = []
        for book in books:
            response = client.post("/api/v1/books/", json=book)
            book_ids.append(response.json()["id"])
        return book_ids

# CONFIGURAÇÃO PYTEST
@pytest.fixture(scope="module")
def test_app():
    """Fixture para aplicação de teste."""
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture(autouse=True)
def reset_database():
    """Reset do banco de dados entre testes."""
    # Em produção, usar banco de teste real
    from app.routers.books import books_db
    books_db.clear()