#!/bin/bash
# scripts/run_development.sh - Script para desenvolvimento

echo "🛠️ Iniciando Biblioteca API em modo desenvolvimento..."

# Instalar dependências
echo "📦 Instalando dependências..."
pip install -r requirements.txt

# Iniciar Redis (se disponível via Docker)
if command -v docker &> /dev/null; then
    echo "🚀 Iniciando Redis..."
    docker run -d --name redis-dev -p 6379:6379 redis:7-alpine || echo "Redis já está rodando"
fi

# Iniciar a aplicação
echo "🚀 Iniciando FastAPI..."
echo "API: http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
echo ""

uvicorn biblioteca_api.app.main:app --host 0.0.0.0 --port 8000 --reload
