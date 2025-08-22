# Makefile para Biblioteca API

.PHONY: help install dev prod test clean logs stop

# Cores para output
RED=\033[0;31m
GREEN=\033[0;32m
YELLOW=\033[1;33m
NC=\033[0m # No Color

help: ## Mostrar esta ajuda
	@echo "$(GREEN)Biblioteca API - Comandos disponíveis:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(YELLOW)%-15s$(NC) %s\n", $$1, $$2}'

install: ## Instalar dependências
	@echo "$(GREEN)📦 Instalando dependências...$(NC)"
	pip install -r requirements.txt

dev: ## Executar em modo desenvolvimento
	@echo "$(GREEN)🛠️ Iniciando modo desenvolvimento...$(NC)"
	chmod +x scripts/run_development.sh
	./scripts/run_development.sh

prod: ## Executar em modo produção (Docker)
	@echo "$(GREEN)🚀 Iniciando modo produção...$(NC)"
	chmod +x scripts/run_production.sh
	./scripts/run_production.sh

test: ## Executar testes
	@echo "$(GREEN)🧪 Executando testes...$(NC)"
	pytest tests/ -v --asyncio-mode=auto

test-cov: ## Executar testes com cobertura
	@echo "$(GREEN)🧪 Executando testes com cobertura...$(NC)"
	pytest tests/ -v --asyncio-mode=auto --cov=biblioteca_api --cov-report=html

lint: ## Verificar código com linting
	@echo "$(GREEN)🔍 Verificando código...$(NC)"
	flake8 biblioteca_api/
	pylint biblioteca_api/

format: ## Formatar código
	@echo "$(GREEN)✨ Formatando código...$(NC)"
	black biblioteca_api/
	isort biblioteca_api/

logs: ## Ver logs da aplicação
	@echo "$(GREEN)📋 Logs da aplicação:$(NC)"
	docker-compose logs -f api

logs-all: ## Ver logs de todos os serviços
	@echo "$(GREEN)📋 Logs de todos os serviços:$(NC)"
	docker-compose logs -f

stop: ## Parar todos os serviços
	@echo "$(RED)🛑 Parando serviços...$(NC)"
	docker-compose down

clean: ## Limpar containers e volumes
	@echo "$(RED)🧹 Limpando containers e volumes...$(NC)"
	docker-compose down -v
	docker system prune -f

status: ## Verificar status dos serviços
	@echo "$(GREEN)📊 Status dos serviços:$(NC)"
	docker-compose ps

build: ## Build dos containers
	@echo "$(GREEN)🔨 Fazendo build...$(NC)"
	docker-compose build

restart: ## Reiniciar serviços
	@echo "$(YELLOW)🔄 Reiniciando serviços...$(NC)"
	docker-compose restart

shell: ## Shell no container da API
	@echo "$(GREEN)🐚 Abrindo shell no container...$(NC)"
	docker-compose exec api /bin/bash
