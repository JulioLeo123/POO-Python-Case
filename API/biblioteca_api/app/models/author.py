# app/models/author.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date
import re

class AuthorBase(BaseModel):
    """
    Modelo base para dados do autor.
    
    CONCEITO: Herança em Pydantic permite reutilização de campos
    comuns entre diferentes contextos (criação, resposta, atualização).
    """
    name: str = Field(
        ..., 
        min_length=2, 
        max_length=100,
        description="Nome completo do autor"
    )
    nationality: Optional[str] = Field(
        None, 
        max_length=50,
        description="Nacionalidade do autor"
    )
    birth_date: Optional[date] = Field(
        None,
        description="Data de nascimento do autor"
    )
    biography: Optional[str] = Field(
        None,
        max_length=2000,
        description="Biografia resumida do autor"
    )
    
    @validator('name')
    def validate_name(cls, v):
        """
        VALIDAÇÃO CUSTOMIZADA: Garante que o nome contenha apenas
        caracteres válidos e tenha formato apropriado.
        
        BENEFÍCIO: Evita dados inconsistentes no banco de dados
        """
        if not re.match(r'^[a-zA-ZÀ-ÿ\s\'-\.]+$', v):
            raise ValueError(
                'Nome deve conter apenas letras, espaços, hífens e apostrofes'
            )
        
        # Normaliza capitalização
        return ' '.join(word.capitalize() for word in v.split())
    
    @validator('birth_date')
    def validate_birth_date(cls, v):
        """
        VALIDAÇÃO DE DATAS: Garante que a data de nascimento
        seja realista (não no futuro, não muito antiga).
        """
        if v is None:
            return v
            
        from datetime import date
        today = date.today()
        
        if v > today:
            raise ValueError('Data de nascimento não pode ser no futuro')
            
        # Assumindo que não temos autores com mais de 150 anos
        min_birth_year = today.year - 150
        if v.year < min_birth_year:
            raise ValueError(f'Data de nascimento deve ser posterior a {min_birth_year}')
            
        return v

class AuthorCreate(AuthorBase):
    """
    Modelo para criação de autor.
    
    CONCEITO: Separação de responsabilidades - dados necessários
    para criação podem diferir dos dados de resposta.
    """
    pass

class AuthorUpdate(BaseModel):
    """
    Modelo para atualização de autor.
    
    CONCEITO: Todos os campos opcionais para permitir
    atualizações parciais (PATCH operations).
    """
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    nationality: Optional[str] = Field(None, max_length=50)
    birth_date: Optional[date] = None
    biography: Optional[str] = Field(None, max_length=2000)

class Author(AuthorBase):
    """
    Modelo completo do autor (resposta da API).
    
    CONCEITO: Inclui campos gerados pelo sistema (ID, timestamps)
    que não estão presentes na criação.
    """
    id: int = Field(..., description="Identificador único do autor")
    books_count: int = Field(0, description="Número de livros publicados")
    
    class Config:
        # Permite criação a partir de ORMs (SQLAlchemy, etc.)
        from_attributes = True
        
        # Exemplo de dados para documentação automática
        schema_extra = {
            "example": {
                "id": 1,
                "name": "Gabriel García Márquez",
                "nationality": "Colombiana",
                "birth_date": "1927-03-06",
                "biography": "Escritor colombiano, ganhador do Prêmio Nobel...",
                "books_count": 12
            }
        }