# app/models/book.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date
from enum import Enum
import re

class BookStatus(str, Enum):
    """
    CONCEITO: Enum para garantir valores válidos de status.
    
    BENEFÍCIO: Type safety e documentação automática dos
    valores aceitos pela API.
    """
    AVAILABLE = "available"
    BORROWED = "borrowed" 
    MAINTENANCE = "maintenance"
    LOST = "lost"

class BookBase(BaseModel):
    """
    Modelo base para livros com validações avançadas.
    """
    title: str = Field(
        ..., 
        min_length=1, 
        max_length=200,
        description="Título do livro"
    )
    isbn: Optional[str] = Field(
        None,
        description="ISBN do livro (10 ou 13 dígitos)"
    )
    author_id: int = Field(
        ...,
        gt=0,
        description="ID do autor do livro"
    )
    publication_year: Optional[int] = Field(
        None,
        description="Ano de publicação"
    )
    pages: Optional[int] = Field(
        None,
        gt=0,
        le=10000,
        description="Número de páginas"
    )
    genre: Optional[str] = Field(
        None,
        max_length=50,
        description="Gênero literário"
    )
    summary: Optional[str] = Field(
        None,
        max_length=5000,
        description="Resumo do livro"
    )
    
    @validator('isbn')
    def validate_isbn(cls, v):
        """
        VALIDAÇÃO COMPLEXA: Valida formato ISBN-10 ou ISBN-13.
        
        CONCEITO: Demonstra como implementar validações específicas
        de domínio usando regex e algoritmos de verificação.
        """
        if v is None:
            return v
            
        # Remove hífens e espaços
        isbn_clean = re.sub(r'[-\s]', '', v)
        
        # Valida ISBN-10
        if len(isbn_clean) == 10:
            if not re.match(r'^\d{9}[\dX]$', isbn_clean):
                raise ValueError('ISBN-10 deve ter 9 dígitos seguidos de um dígito ou X')
            
            # Algoritmo de verificação ISBN-10
            total = 0
            for i, digit in enumerate(isbn_clean[:9]):
                total += int(digit) * (10 - i)
            
            check_digit = isbn_clean[9]
            if check_digit == 'X':
                total += 10
            else:
                total += int(check_digit)
                
            if total % 11 != 0:
                raise ValueError('ISBN-10 inválido (falha na verificação)')
                
        # Valida ISBN-13
        elif len(isbn_clean) == 13:
            if not re.match(r'^\d{13}$', isbn_clean):
                raise ValueError('ISBN-13 deve ter exatamente 13 dígitos')
            
            # Algoritmo de verificação ISBN-13
            total = 0
            for i, digit in enumerate(isbn_clean[:12]):
                multiplier = 1 if i % 2 == 0 else 3
                total += int(digit) * multiplier
            
            check_digit = (10 - (total % 10)) % 10
            if int(isbn_clean[12]) != check_digit:
                raise ValueError('ISBN-13 inválido (falha na verificação)')
        else:
            raise ValueError('ISBN deve ter 10 ou 13 dígitos')
            
        return isbn_clean
    
    @validator('publication_year')
    def validate_publication_year(cls, v):
        """
        VALIDAÇÃO TEMPORAL: Garante que o ano de publicação
        seja realista (não no futuro, não muito antigo).
        """
        if v is None:
            return v
            
        from datetime import date
        current_year = date.today().year
        
        if v > current_year:
            raise ValueError('Ano de publicação não pode ser no futuro')
            
        # Assumindo que não catalogamos livros anteriores a 1000 d.C.
        if v < 1000:
            raise ValueError('Ano de publicação deve ser posterior a 1000')
            
        return v

class BookCreate(BookBase):
    """Modelo para criação de livro."""
    status: BookStatus = Field(
        default=BookStatus.AVAILABLE,
        description="Status inicial do livro"
    )

class BookUpdate(BaseModel):
    """Modelo para atualização parcial de livro."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    isbn: Optional[str] = None
    author_id: Optional[int] = Field(None, gt=0)
    publication_year: Optional[int] = None
    pages: Optional[int] = Field(None, gt=0, le=10000)
    genre: Optional[str] = Field(None, max_length=50)
    summary: Optional[str] = Field(None, max_length=5000)
    status: Optional[BookStatus] = None

class Book(BookBase):
    """Modelo completo do livro (resposta da API)."""
    id: int = Field(..., description="Identificador único do livro")
    status: BookStatus = Field(..., description="Status atual do livro")
    created_at: date = Field(..., description="Data de cadastro")
    updated_at: Optional[date] = Field(None, description="Data da última atualização")
    
    # Dados enriquecidos de APIs externas
    external_rating: Optional[float] = Field(
        None, 
        ge=0, 
        le=10,
        description="Avaliação de APIs externas"
    )
    cover_url: Optional[str] = Field(
        None,
        description="URL da capa do livro"
    )
    
    class Config:
        from_attributes = True
        schema_extra = {
            "example": {
                "id": 1,
                "title": "Cem Anos de Solidão",
                "isbn": "9788535902770",
                "author_id": 1,
                "publication_year": 1967,
                "pages": 448,
                "genre": "Realismo Mágico",
                "summary": "A história da família Buendía...",
                "status": "available",
                "created_at": "2024-01-15",
                "external_rating": 8.5,
                "cover_url": "https://example.com/cover.jpg"
            }
        }