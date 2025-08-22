#!/bin/bash
# scripts/run_production.sh - Script para produção

echo "🚀 Iniciando Biblioteca API em modo produção..."

# Verificar se Docker está instalado
if ! command -v docker &> /dev/null; then
    echo "❌ Docker não encontrado. Instale o Docker primeiro."
    exit 1
fi

# Verificar se Docker Compose está instalado
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose não encontrado. Instale o Docker Compose primeiro."
    exit 1
fi

# Build e start dos containers
echo "🔨 Fazendo build dos containers..."
docker-compose build

echo "🚀 Iniciando serviços..."
docker-compose up -d

echo "⏳ Aguardando serviços ficarem prontos..."
sleep 10

# Verificar se os serviços estão rodando
echo "🔍 Verificando status dos serviços..."
docker-compose ps

echo ""
echo "✅ Biblioteca API está rodando!"
echo ""
echo "📋 URLs dos serviços:"
echo "API: http://localhost"
echo "Docs: http://localhost/docs"
echo "Prometheus: http://localhost:9090"
echo "Grafana: http://localhost:3000 (admin/admin123)"
echo ""
echo "📊 Para ver logs:"
echo "docker-compose logs -f api"
echo ""
echo "🛑 Para parar:"
echo "docker-compose down"
