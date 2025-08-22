# app/routers/books.py
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional
from datetime import date
import logging

from ..models.book import Book, BookCreate, BookUpdate, BookStatus
from ..services.external_apis import BookEnrichmentService
from ..services.cache import CacheService

# CONCEITO: APIRouter permite organizar rotas relacionadas
# em módulos separados, facilitando manutenção e scaling
router = APIRouter(
    prefix="/books",
    tags=["books"],
    responses={404: {"description": "Livro não encontrado"}}
)

# Simulação de banco de dados em memória para demonstração
# Em produção, usar SQLAlchemy, MongoDB, etc.
books_db: List[Book] = []
next_book_id = 1

# Dependências injetadas
def get_enrichment_service() -> BookEnrichmentService:
    """
    CONCEITO: Dependency Injection Pattern
    
    BENEFÍCIO: Permite fácil substituição de implementações
    para testes, diferentes ambientes, etc.
    """
    return BookEnrichmentService()

def get_cache_service() -> CacheService:
    """Dependência para serviço de cache."""
    return CacheService()

@router.post(
    "/",
    response_model=Book,
    status_code=status.HTTP_201_CREATED,
    summary="Criar um novo livro",
    description="Cria um novo livro no catálogo da biblioteca"
)
async def create_book(
    book_data: BookCreate,
    enrichment_service: BookEnrichmentService = Depends(get_enrichment_service)
):
    """
    OPERAÇÃO CREATE (POST): Cria um novo recurso livro.
    
    CONCEITOS DEMONSTRADOS:
    - Validação automática via Pydantic
    - Enriquecimento de dados via API externa
    - Response model para documentação
    - Status code apropriado (201 Created)
    """
    global next_book_id
    
    try:
        # VALIDAÇÃO DE NEGÓCIO: Verifica se author_id existe
        # Em produção, isso seria uma consulta ao banco
        if not _author_exists(book_data.author_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Autor com ID {book_data.author_id} não encontrado"
            )
        
        # ENRIQUECIMENTO DE DADOS: Busca informações externas
        external_data = await enrichment_service.enrich_book_data(
            title=book_data.title,
            isbn=book_data.isbn
        )
        
        # CRIAÇÃO DO OBJETO: Combina dados locais e externos
        new_book = Book(
            id=next_book_id,
            **book_data.dict(),
            created_at=date.today(),
            external_rating=external_data.get('rating'),
            cover_url=external_data.get('cover_url')
        )
        
        books_db.append(new_book)
        next_book_id += 1
        
        logging.info(f"Livro criado com sucesso: ID {new_book.id}")
        return new_book
        
    except Exception as e:
        logging.error(f"Erro ao criar livro: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno do servidor ao criar livro"
        )

@router.get(
    "/",
    response_model=List[Book],
    summary="Listar livros",
    description="Lista todos os livros com filtros opcionais"
)
async def list_books(
    status_filter: Optional[BookStatus] = Query(
        None, 
        description="Filtrar por status do livro"
    ),
    genre: Optional[str] = Query(
        None, 
        description="Filtrar por gênero"
    ),
    author_id: Optional[int] = Query(
        None, 
        description="Filtrar por autor"
    ),
    limit: int = Query(
        100, 
        ge=1, 
        le=1000, 
        description="Número máximo de resultados"
    ),
    offset: int = Query(
        0, 
        ge=0, 
        description="Número de registros a pular"
    ),
    cache_service: CacheService = Depends(get_cache_service)
):
    """
    OPERAÇÃO READ (GET): Lista recursos com filtros e paginação.
    
    CONCEITOS DEMONSTRADOS:
    - Query parameters para filtros
    - Paginação com limit/offset
    - Cache para otimização
    - Documentação automática de parâmetros
    """
    
    # CHAVE DE CACHE: Combina todos os parâmetros
    cache_key = f"books_list:{status_filter}:{genre}:{author_id}:{limit}:{offset}"
    
    # TENTATIVA DE CACHE: Verifica se resultado está cached
    cached_result = await cache_service.get(cache_key)
    if cached_result:
        logging.info(f"Cache hit para listagem de livros: {cache_key}")
        return cached_result
    
    # APLICAÇÃO DE FILTROS: Usa list comprehension para eficiência
    filtered_books = books_db
    
    if status_filter:
        filtered_books = [b for b in filtered_books if b.status == status_filter]
    
    if genre:
        filtered_books = [
            b for b in filtered_books 
            if b.genre and genre.lower() in b.genre.lower()
        ]
    
    if author_id:
        filtered_books = [b for b in filtered_books if b.author_id == author_id]
    
    # PAGINAÇÃO: Aplica offset e limit
    paginated_books = filtered_books[offset:offset + limit]
    
    # ARMAZENAMENTO EM CACHE: Cache por 5 minutos
    await cache_service.set(cache_key, paginated_books, expire=300)
    
    logging.info(f"Listagem retornada: {len(paginated_books)} livros")
    return paginated_books

@router.get(
    "/{book_id}",
    response_model=Book,
    summary="Obter livro por ID",
    description="Retorna um livro específico pelo seu ID"
)
async def get_book(
    book_id: int,
    cache_service: CacheService = Depends(get_cache_service)
):
    """
    OPERAÇÃO READ (GET): Obtém um recurso específico.
    
    CONCEITOS DEMONSTRADOS:
    - Path parameter tipado
    - Cache individual de recursos
    - Tratamento de erro 404
    """
    
    cache_key = f"book:{book_id}"
    
    # VERIFICAÇÃO DE CACHE
    cached_book = await cache_service.get(cache_key)
    if cached_book:
        return cached_book
    
    # BUSCA NO "BANCO DE DADOS"
    book = _find_book_by_id(book_id)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {book_id} não encontrado"
        )
    
    # ARMAZENAMENTO EM CACHE
    await cache_service.set(cache_key, book, expire=600)
    
    return book

@router.put(
    "/{book_id}",
    response_model=Book,
    summary="Atualizar livro completamente",
    description="Substitui todos os dados de um livro"
)
async def update_book_full(
    book_id: int,
    book_update: BookCreate,  # Requer todos os campos
    cache_service: CacheService = Depends(get_cache_service)
):
    """
    OPERAÇÃO UPDATE (PUT): Substituição completa do recurso.
    
    CONCEITO REST: PUT deve substituir o recurso inteiro,
    não apenas campos específicos.
    """
    
    book = _find_book_by_id(book_id)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {book_id} não encontrado"
        )
    
    # VALIDAÇÃO DE NEGÓCIO
    if not _author_exists(book_update.author_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Autor com ID {book_update.author_id} não encontrado"
        )
    
    # ATUALIZAÇÃO COMPLETA: Preserva ID e metadados
    updated_book = Book(
        id=book.id,
        **book_update.dict(),
        created_at=book.created_at,
        updated_at=date.today(),
        external_rating=book.external_rating,
        cover_url=book.cover_url
    )
    
    # SUBSTITUIÇÃO NO "BANCO"
    book_index = next(i for i, b in enumerate(books_db) if b.id == book_id)
    books_db[book_index] = updated_book
    
    # INVALIDAÇÃO DE CACHE
    await cache_service.delete(f"book:{book_id}")
    await cache_service.delete_pattern("books_list:*")
    
    logging.info(f"Livro {book_id} atualizado completamente")
    return updated_book

@router.patch(
    "/{book_id}",
    response_model=Book,
    summary="Atualizar livro parcialmente",
    description="Atualiza apenas os campos fornecidos"
)
async def update_book_partial(
    book_id: int,
    book_update: BookUpdate,  # Campos opcionais
    cache_service: CacheService = Depends(get_cache_service)
):
    """
    OPERAÇÃO UPDATE (PATCH): Atualização parcial do recurso.
    
    CONCEITO REST: PATCH permite atualizar apenas campos
    específicos sem afetar o restante do recurso.
    """
    
    book = _find_book_by_id(book_id)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {book_id} não encontrado"
        )
    
    # DADOS PARA ATUALIZAÇÃO: Remove campos None
    update_data = book_update.dict(exclude_unset=True)
    
    # VALIDAÇÃO CONDICIONAL: Só valida author_id se fornecido
    if 'author_id' in update_data and not _author_exists(update_data['author_id']):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Autor com ID {update_data['author_id']} não encontrado"
        )
    
    # ATUALIZAÇÃO PARCIAL: Usa copy/update pattern
    book_dict = book.dict()
    book_dict.update(update_data)
    book_dict['updated_at'] = date.today()
    
    updated_book = Book(**book_dict)
    
    # SUBSTITUIÇÃO NO "BANCO"
    book_index = next(i for i, b in enumerate(books_db) if b.id == book_id)
    books_db[book_index] = updated_book
    
    # INVALIDAÇÃO DE CACHE
    await cache_service.delete(f"book:{book_id}")
    await cache_service.delete_pattern("books_list:*")
    
    logging.info(f"Livro {book_id} atualizado parcialmente: {list(update_data.keys())}")
    return updated_book

@router.delete(
    "/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover livro",
    description="Remove um livro do catálogo"
)
async def delete_book(
    book_id: int,
    cache_service: CacheService = Depends(get_cache_service)
):
    """
    OPERAÇÃO DELETE: Remove recurso do sistema.
    
    CONCEITOS DEMONSTRADOS:
    - Status 204 No Content para deleção bem-sucedida
    - Validação de regras de negócio
    - Limpeza de cache relacionado
    """
    
    book = _find_book_by_id(book_id)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {book_id} não encontrado"
        )
    
    # REGRA DE NEGÓCIO: Não permite deletar livros emprestados
    if book.status == BookStatus.BORROWED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível deletar livro emprestado"
        )
    
    # REMOÇÃO DO "BANCO"
    global books_db
    books_db = [b for b in books_db if b.id != book_id]
    
    # LIMPEZA DE CACHE
    await cache_service.delete(f"book:{book_id}")
    await cache_service.delete_pattern("books_list:*")
    
    logging.info(f"Livro {book_id} removido com sucesso")
    # Retorno vazio com status 204

# FUNÇÕES AUXILIARES
def _find_book_by_id(book_id: int) -> Optional[Book]:
    """Busca livro por ID no 'banco de dados'."""
    return next((book for book in books_db if book.id == book_id), None)

def _author_exists(author_id: int) -> bool:
    """Verifica se autor existe (simulado)."""
    # Em produção, seria uma consulta ao banco
    return author_id > 0  # Simulação simples