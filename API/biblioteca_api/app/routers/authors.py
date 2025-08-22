# app/routers/authors.py
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional
import logging

from ..models.author import Author, AuthorCreate, AuthorUpdate

# CONCEITO: APIRouter para organização modular de rotas
router = APIRouter(
    prefix="/authors",
    tags=["authors"],
    responses={404: {"description": "Autor não encontrado"}}
)

# Simulação de banco de dados em memória
authors_db: List[Author] = []
next_author_id = 1

@router.post(
    "/",
    response_model=Author,
    status_code=status.HTTP_201_CREATED,
    summary="Criar um novo autor",
    description="Adiciona um novo autor ao sistema"
)
async def create_author(author_data: AuthorCreate):
    """Cria um novo autor."""
    global next_author_id
    
    try:
        new_author = Author(
            id=next_author_id,
            **author_data.dict()
        )
        
        authors_db.append(new_author)
        next_author_id += 1
        
        logging.info(f"Autor criado com sucesso: ID {new_author.id}")
        return new_author
        
    except Exception as e:
        logging.error(f"Erro ao criar autor: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno do servidor ao criar autor"
        )

@router.get(
    "/",
    response_model=List[Author],
    summary="Listar autores",
    description="Lista todos os autores com filtros opcionais"
)
async def list_authors(
    name: Optional[str] = Query(None, description="Filtrar por nome"),
    nationality: Optional[str] = Query(None, description="Filtrar por nacionalidade"),
    limit: int = Query(100, ge=1, le=1000, description="Número máximo de resultados"),
    offset: int = Query(0, ge=0, description="Número de registros a pular")
):
    """Lista autores com filtros opcionais."""
    filtered_authors = authors_db
    
    if name:
        filtered_authors = [
            a for a in filtered_authors 
            if name.lower() in a.name.lower()
        ]
    
    if nationality:
        filtered_authors = [
            a for a in filtered_authors 
            if a.nationality and nationality.lower() in a.nationality.lower()
        ]
    
    paginated_authors = filtered_authors[offset:offset + limit]
    
    logging.info(f"Listagem retornada: {len(paginated_authors)} autores")
    return paginated_authors

@router.get(
    "/{author_id}",
    response_model=Author,
    summary="Obter autor por ID",
    description="Retorna um autor específico pelo seu ID"
)
async def get_author(author_id: int):
    """Obtém um autor específico por ID."""
    author = _find_author_by_id(author_id)
    if not author:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Autor com ID {author_id} não encontrado"
        )
    
    return author

@router.put(
    "/{author_id}",
    response_model=Author,
    summary="Atualizar autor completamente",
    description="Substitui todos os dados de um autor"
)
async def update_author_full(author_id: int, author_update: AuthorCreate):
    """Atualiza completamente um autor."""
    author = _find_author_by_id(author_id)
    if not author:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Autor com ID {author_id} não encontrado"
        )
    
    updated_author = Author(
        id=author.id,
        **author_update.dict()
    )
    
    author_index = next(i for i, a in enumerate(authors_db) if a.id == author_id)
    authors_db[author_index] = updated_author
    
    logging.info(f"Autor {author_id} atualizado completamente")
    return updated_author

@router.patch(
    "/{author_id}",
    response_model=Author,
    summary="Atualizar autor parcialmente",
    description="Atualiza apenas os campos fornecidos"
)
async def update_author_partial(author_id: int, author_update: AuthorUpdate):
    """Atualiza parcialmente um autor."""
    author = _find_author_by_id(author_id)
    if not author:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Autor com ID {author_id} não encontrado"
        )
    
    update_data = author_update.dict(exclude_unset=True)
    
    author_dict = author.dict()
    author_dict.update(update_data)
    
    updated_author = Author(**author_dict)
    
    author_index = next(i for i, a in enumerate(authors_db) if a.id == author_id)
    authors_db[author_index] = updated_author
    
    logging.info(f"Autor {author_id} atualizado parcialmente: {list(update_data.keys())}")
    return updated_author

@router.delete(
    "/{author_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover autor",
    description="Remove um autor do sistema"
)
async def delete_author(author_id: int):
    """Remove um autor."""
    author = _find_author_by_id(author_id)
    if not author:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Autor com ID {author_id} não encontrado"
        )
    
    global authors_db
    authors_db = [a for a in authors_db if a.id != author_id]
    
    logging.info(f"Autor {author_id} removido com sucesso")

def _find_author_by_id(author_id: int) -> Optional[Author]:
    """Busca autor por ID."""
    return next((author for author in authors_db if author.id == author_id), None)