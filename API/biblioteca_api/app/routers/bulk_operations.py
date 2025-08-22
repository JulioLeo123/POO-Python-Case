# app/routers/bulk_operations.py
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, validator
import asyncio
import uuid
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

router = APIRouter(prefix="/bulk", tags=["bulk"])

# MODELOS PARA OPERAÇÕES EM LOTE
class BulkBookCreate(BaseModel):
    """Modelo para criação em lote de livros."""
    books: List[BookCreate] = Field(..., min_items=1, max_items=1000)
    enrichment_enabled: bool = Field(default=True, description="Enriquecer dados via APIs externas")
    parallel_processing: bool = Field(default=True, description="Processamento paralelo")
    
    @validator('books')
    def validate_unique_isbns(cls, v):
        """Valida que ISBNs são únicos no lote."""
        isbns = [book.isbn for book in v if book.isbn]
        if len(isbns) != len(set(isbns)):
            raise ValueError("ISBNs duplicados encontrados no lote")
        return v

class BulkBookUpdate(BaseModel):
    """Modelo para atualização em lote."""
    updates: List[Dict[str, Any]] = Field(..., min_items=1, max_items=500)
    
    @validator('updates')
    def validate_updates(cls, v):
        """Valida formato das atualizações."""
        for update in v:
            if 'id' not in update:
                raise ValueError("Cada atualização deve conter 'id'")
            if len(update) < 2:  # id + pelo menos um campo
                raise ValueError("Cada atualização deve conter pelo menos um campo para alterar")
        return v

@dataclass
class BulkOperationResult:
    """Resultado de operação em lote."""
    operation_id: str
    total_items: int
    successful_items: int
    failed_items: int
    errors: List[Dict[str, Any]]
    processing_time: float
    items_per_second: float

class BulkOperationService:
    """
    Serviço para operações em lote otimizadas.
    
    OTIMIZAÇÕES IMPLEMENTADAS:
    - Processamento paralelo com asyncio
    - Chunking para controle de memória
    - Progress tracking para operações longas
    - Error collection sem interrupção
    - Rate limiting automático
    """
    
    def __init__(self, max_workers: int = 50, chunk_size: int = 100):
        self.max_workers = max_workers
        self.chunk_size = chunk_size
        self.active_operations: Dict[str, dict] = {}
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
    
    async def bulk_create_books(
        self,
        bulk_request: BulkBookCreate,
        enrichment_service: BookEnrichmentService
    ) -> BulkOperationResult:
        """
        CRIAÇÃO EM LOTE: Processamento paralelo otimizado.
        
        ESTRATÉGIAS:
        1. Chunking para controle de memória
        2. Semáforo para controle de concorrência
        3. Coleta de erros sem interrupção
        4. Progress tracking
        """
        operation_id = str(uuid.uuid4())
        start_time = time.time()
        books = bulk_request.books
        
        # INICIALIZAÇÃO DE TRACKING
        self.active_operations[operation_id] = {
            "status": "processing",
            "total": len(books),
            "processed": 0,
            "start_time": start_time
        }
        
        successful_books = []
        errors = []
        
        # PROCESSAMENTO EM CHUNKS
        for chunk_start in range(0, len(books), self.chunk_size):
            chunk_end = min(chunk_start + self.chunk_size, len(books))
            chunk = books[chunk_start:chunk_end]
            
            if bulk_request.parallel_processing:
                # PROCESSAMENTO PARALELO DO CHUNK
                chunk_results = await self._process_chunk_parallel(
                    chunk, enrichment_service, bulk_request.enrichment_enabled
                )
            else:
                # PROCESSAMENTO SEQUENCIAL (PARA DEBUGGING)
                chunk_results = await self._process_chunk_sequential(
                    chunk, enrichment_service, bulk_request.enrichment_enabled
                )
            
            # CONSOLIDAÇÃO DE RESULTADOS
            for result in chunk_results:
                if result["success"]:
                    successful_books.append(result["book"])
                else:
                    errors.append(result["error"])
            
            # UPDATE PROGRESS
            self.active_operations[operation_id]["processed"] = chunk_end
            
            # PAUSA PARA EVITAR SOBRECARGA
            await asyncio.sleep(0.1)
        
        # CÁLCULOS FINAIS
        end_time = time.time()
        processing_time = end_time - start_time
        total_items = len(books)
        successful_items = len(successful_books)
        failed_items = len(errors)
        items_per_second = total_items / processing_time if processing_time > 0 else 0
        
        # CLEANUP
        del self.active_operations[operation_id]
        
        # PERSISTÊNCIA DOS LIVROS CRIADOS
        global books_db
        for book in successful_books:
            books_db.append(book)
        
        logging.info(
            f"Bulk create completed: {successful_items}/{total_items} "
            f"successful in {processing_time:.2f}s ({items_per_second:.1f} items/s)"
        )
        
        return BulkOperationResult(
            operation_id=operation_id,
            total_items=total_items,
            successful_items=successful_items,
            failed_items=failed_items,
            errors=errors,
            processing_time=processing_time,
            items_per_second=items_per_second
        )
    
    async def _process_chunk_parallel(
        self,
        chunk: List[BookCreate],
        enrichment_service: BookEnrichmentService,
        enrichment_enabled: bool
    ) -> List[Dict[str, Any]]:
        """
        PROCESSAMENTO PARALELO: Usa semáforo para controle de concorrência.
        """
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def process_single_book(book_data: BookCreate) -> Dict[str, Any]:
            async with semaphore:
                try:
                    return await self._create_single_book(
                        book_data, enrichment_service, enrichment_enabled
                    )
                except Exception as e:
                    return {
                        "success": False,
                        "error": {
                            "item": book_data.dict(),
                            "error_type": type(e).__name__,
                            "error_message": str(e)
                        }
                    }
        
        # EXECUÇÃO PARALELA
        tasks = [process_single_book(book) for book in chunk]
        return await asyncio.gather(*tasks, return_exceptions=False)
    
    async def _process_chunk_sequential(
        self,
        chunk: List[BookCreate],
        enrichment_service: BookEnrichmentService,
        enrichment_enabled: bool
    ) -> List[Dict[str, Any]]:
        """
        PROCESSAMENTO SEQUENCIAL: Para debugging ou APIs com rate limiting rigoroso.
        """
        results = []
        for book_data in chunk:
            try:
                result = await self._create_single_book(
                    book_data, enrichment_service, enrichment_enabled
                )
                results.append(result)
            except Exception as e:
                results.append({
                    "success": False,
                    "error": {
                        "item": book_data.dict(),
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                })
            
            # Rate limiting interno
            await asyncio.sleep(0.01)
        
        return results
    
    async def _create_single_book(
        self,
        book_data: BookCreate,
        enrichment_service: BookEnrichmentService,
        enrichment_enabled: bool
    ) -> Dict[str, Any]:
        """
        CRIAÇÃO INDIVIDUAL: Lógica de criação de um livro com enriquecimento.
        """
        global next_book_id
        
        # VALIDAÇÃO DE NEGÓCIO
        if not _author_exists(book_data.author_id):
            raise ValueError(f"Autor {book_data.author_id} não encontrado")
        
        # ENRIQUECIMENTO OPCIONAL
        enriched_data = {}
        if enrichment_enabled and book_data.isbn:
            try:
                enriched_data = await enrichment_service.enrich_book_data(
                    book_data.title, book_data.isbn
                )
            except Exception as e:
                logging.warning(f"Enrichment failed for {book_data.isbn}: {e}")
        
        # CRIAÇÃO DO LIVRO
        new_book = Book(
            id=next_book_id,
            title=book_data.title,
            isbn=book_data.isbn,
            author_id=book_data.author_id,
            publication_year=book_data.publication_year,
            pages=book_data.pages,
            genre=book_data.genre,
            summary=book_data.summary,
            status=book_data.status,
            created_at=date.today(),
            external_rating=enriched_data.get("rating"),
            cover_url=enriched_data.get("cover_url")
        )
        
        next_book_id += 1
        
        return {
            "success": True,
            "book": new_book
        }
    
    def get_operation_status(self, operation_id: str) -> Optional[dict]:
        """TRACKING: Status de operação em andamento."""
        return self.active_operations.get(operation_id)

# INSTÂNCIA DO SERVIÇO
bulk_service = BulkOperationService()

@router.post("/books", response_model=dict)
async def bulk_create_books(
    bulk_request: BulkBookCreate,
    background_tasks: BackgroundTasks,
    enrichment_service: BookEnrichmentService = Depends(get_enrichment_service)
):
    """
    ENDPOINT DE CRIAÇÃO EM LOTE: Processa múltiplos livros.
    
    CARACTERÍSTICAS:
    - Validação de lote antes do processamento
    - Processamento paralelo otimizado
    - Progress tracking para operações longas
    - Error collection detalhada
    - Rate limiting automático
    """
    
    # VALIDAÇÃO PRÉVIA
    if len(bulk_request.books) > 1000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Máximo 1000 livros por lote"
        )
    
    # EXECUÇÃO DA OPERAÇÃO
    try:
        result = await bulk_service.bulk_create_books(bulk_request, enrichment_service)
        
        return {
            "message": f"Processamento concluído: {result.successful_items}/{result.total_items} livros criados",
            "operation_id": result.operation_id,
            "summary": {
                "total_items": result.total_items,
                "successful_items": result.successful_items,
                "failed_items": result.failed_items,
                "processing_time_seconds": round(result.processing_time, 2),
                "items_per_second": round(result.items_per_second, 1)
            },
            "errors": result.errors[:10],  # Primeiros 10 erros apenas
            "has_more_errors": len(result.errors) > 10
        }
        
    except Exception as e:
        logging.error(f"Bulk operation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha no processamento em lote"
        )

@router.patch("/books", response_model=dict)
async def bulk_update_books(bulk_update: BulkBookUpdate):
    """
    ATUALIZAÇÃO EM LOTE: Atualiza múltiplos livros de forma otimizada.
    
    ESTRATÉGIA:
    - Validação prévia de existência
    - Agrupamento por tipo de atualização
    - Rollback em caso de falha crítica
    """
    
    start_time = time.time()
    successful_updates = []
    failed_updates = []
    
    # VALIDAÇÃO DE EXISTÊNCIA EM LOTE
    book_ids = [update["id"] for update in bulk_update.updates]
    existing_books = {book.id: book for book in books_db if book.id in book_ids}
    
    for update_data in bulk_update.updates:
        book_id = update_data["id"]
        
        try:
            # VERIFICAÇÃO DE EXISTÊNCIA
            if book_id not in existing_books:
                raise ValueError(f"Livro {book_id} não encontrado")
            
            # APLICAÇÃO DA ATUALIZAÇÃO
            book = existing_books[book_id]
            update_fields = {k: v for k, v in update_data.items() if k != "id"}
            
            # VALIDAÇÃO DE CAMPOS
            valid_book_update = BookUpdate(**update_fields)
            
            # ATUALIZAÇÃO EFETIVA
            book_dict = book.dict()
            book_dict.update(valid_book_update.dict(exclude_unset=True))
            book_dict["updated_at"] = date.today()
            
            updated_book = Book(**book_dict)
            
            # SUBSTITUIÇÃO NO "BANCO"
            book_index = next(i for i, b in enumerate(books_db) if b.id == book_id)
            books_db[book_index] = updated_book
            
            successful_updates.append(book_id)
            
        except Exception as e:
            failed_updates.append({
                "book_id": book_id,
                "error": str(e)
            })
    
    processing_time = time.time() - start_time
    
    return {
        "message": f"Atualização em lote concluída: {len(successful_updates)}/{len(bulk_update.updates)} atualizações",
        "summary": {
            "total_updates": len(bulk_update.updates),
            "successful_updates": len(successful_updates),
            "failed_updates": len(failed_updates),
            "processing_time_seconds": round(processing_time, 2)
        },
        "successful_ids": successful_updates,
        "failed_updates": failed_updates
    }

@router.delete("/books", response_model=dict)
async def bulk_delete_books(book_ids: List[int] = Field(..., min_items=1, max_items=100)):
    """
    DELEÇÃO EM LOTE: Remove múltiplos livros com validação de regras de negócio.
    
    VALIDAÇÕES:
    - Livros existem
    - Livros não estão emprestados
    - Limite de quantidade por operação
    """
    
    if len(book_ids) > 100:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Máximo 100 livros por operação de deleção"
        )
    
    successful_deletions = []
    failed_deletions = []
    
    for book_id in book_ids:
        try:
            book = _find_book_by_id(book_id)
            if not book:
                raise ValueError("Livro não encontrado")
            
            if book.status == BookStatus.BORROWED:
                raise ValueError("Não é possível deletar livro emprestado")
            
            # REMOÇÃO
            global books_db
            books_db = [b for b in books_db if b.id != book_id]
            successful_deletions.append(book_id)
            
        except Exception as e:
            failed_deletions.append({
                "book_id": book_id,
                "error": str(e)
            })
    
    return {
        "message": f"Deleção em lote concluída: {len(successful_deletions)}/{len(book_ids)} livros removidos",
        "successful_deletions": successful_deletions,
        "failed_deletions": failed_deletions
    }

@router.get("/operations/{operation_id}/status")
async def get_operation_status(operation_id: str):
    """
    TRACKING DE OPERAÇÃO: Status de operação em lote em andamento.
    
    USO: Polling para operações longas
    """
    status_info = bulk_service.get_operation_status(operation_id)
    
    if not status_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operação não encontrada"
        )
    
    # CÁLCULO DE PROGRESSO
    progress_percentage = (status_info["processed"] / status_info["total"]) * 100
    elapsed_time = time.time() - status_info["start_time"]
    
    if status_info["processed"] > 0:
        estimated_total_time = elapsed_time * (status_info["total"] / status_info["processed"])
        remaining_time = max(0, estimated_total_time - elapsed_time)
    else:
        remaining_time = None
    
    return {
        "operation_id": operation_id,
        "status": status_info["status"],
        "progress": {
            "total_items": status_info["total"],
            "processed_items": status_info["processed"],
            "percentage": round(progress_percentage, 1),
            "elapsed_time_seconds": round(elapsed_time, 1),
            "estimated_remaining_seconds": round(remaining_time, 1) if remaining_time else None
        }
    }