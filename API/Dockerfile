FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY biblioteca_api/ ./biblioteca_api/

# Criar usuário não-root
RUN useradd --create-home --shell /bin/bash app
USER app

# Expor porta
EXPOSE 8000

# Comando para produção com Gunicorn
CMD ["gunicorn", "biblioteca_api.app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
