.PHONY: help install dev run build up down logs clean test deploy restart-app deploy-dev deploy-prod

# Default variables for deployment
ifndef u
u:=truong95k58
endif

ifndef env
env:=dev
endif

ifndef ssh_key
ssh_key:=/home/sotatek/.ssh/id_ecdsa_truong95k58
endif

help:
	@echo "Available commands:"
	@echo ""
	@echo "Local Development:"
	@echo "  make install     - Install dependencies with uv"
	@echo "  make dev         - Run API in development mode (hot reload)"
	@echo "  make run         - Run API in production mode"
	@echo "  make test        - Test API endpoints"
	@echo ""
	@echo "Docker:"
	@echo "  make build       - Build Docker image"
	@echo "  make up          - Start all services with docker-compose"
	@echo "  make down        - Stop all services"
	@echo "  make logs        - View logs from all services"
	@echo "  make clean       - Clean up containers and volumes"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy h=<host> dir=<remote_dir>  - Deploy to remote server"
	@echo "  make restart-app h=<host> dir=<remote_dir> - Restart app on remote server"
	@echo "  make deploy-dev  - Deploy to dev server (34.143.173.34)"
	@echo "  make deploy-prod - Deploy to production server"
	@echo "  make start-all-remote h=<host> dir=<remote_dir> - Start all services on remote"
	@echo "  make start-all-local - Start all services locally with docker-compose-full.yml"
	@echo "  make sync-qdrant-from-remote h=<host> dir=<remote_dir> - Download Qdrant data from remote"
	@echo "  make sync-qdrant-to-remote h=<host> dir=<remote_dir> - Upload Qdrant data to remote"
	@echo ""
	@echo "Examples:"
	@echo "  make deploy h=34.143.173.34 dir=/home/truong95k58/unified_api"
	@echo "  make deploy-dev"

install:
	@echo "📦 Installing dependencies with uv..."
	uv sync

dev:
	@echo "🔧 Starting development server..."
	./start.sh dev

run:
	@echo "🚀 Starting production server..."
	./start.sh prod

build:
	@echo "🏗️  Building Docker image..."
	docker-compose build

up:
	@echo "🚀 Starting all services..."
	docker-compose up -d
	@echo "✓ Services started!"
	@echo "  - Unified API: http://localhost:8080"
	@echo "  - API Docs: http://localhost:8080/docs"
	@echo "  - Flower (Celery Monitor): http://localhost:5555"
	@echo "  - RabbitMQ Management: http://localhost:15672 (admin/admin123)"

down:
	@echo "⏹️  Stopping all services..."
	docker-compose down

logs:
	@echo "📋 Viewing logs..."
	docker-compose logs -f unified-api

clean:
	@echo "🧹 Cleaning up..."
	docker-compose down -v
	@echo "✓ Cleanup complete!"

test:
	@echo "🧪 Testing API endpoints..."
	@echo "\n1. Testing root endpoint..."
	@curl -s http://localhost:8080/ | jq
	@echo "\n2. Testing health check..."
	@curl -s http://localhost:8080/health | jq
	@echo "\n3. Testing services list..."
	@curl -s http://localhost:8080/services | jq

# ============================================================================
# Deployment commands
# ============================================================================
deploy:
	@echo "📦 Deploying to $(u)@$(h):$(dir)..."
	ssh -i $(ssh_key) $(u)@$(h) "mkdir -p $(dir)"
	rsync -avhzL --delete \
				-e "ssh -i $(ssh_key)" \
				--no-perms --no-owner --no-group \
				--exclude .git \
				--exclude .idea \
				--exclude .env \
				--exclude out \
				--exclude data_ver2 \
				--exclude logs \
				--exclude __pycache__ \
				--exclude .pytest_cache \
				--exclude .venv \
				--exclude rag_service/.venv \
				--exclude classifier_service/.venv \
				--exclude qdrant_data \
				--exclude profiles \
				--exclude output \
				. $(u)@$(h):$(dir)/
	@echo "✓ Deployment complete!"

restart-app:
	@echo "🔄 Restarting application on $(h)..."
	ssh -i $(ssh_key) $(u)@$(h) "cd $(dir) && docker compose -f docker-compose.server.yml down && docker compose -f docker-compose.server.yml up -d --build"
	@echo "✓ Application restarted!"
	@echo "  Check status: ssh -i $(ssh_key) $(u)@$(h) 'cd $(dir) && docker compose -f docker-compose.server.yml ps'"

deploy-dev:
	@echo "🚀 Deploying to DEV server (34.143.173.34)..."
	make deploy h=34.143.173.34 dir=/home/truong95k58/unified_api && \
	make restart-app h=34.143.173.34 dir=/home/truong95k58/unified_api
	@echo ""
	@echo "✓ Dev deployment complete!"
	@echo ""
	@echo "🌐 Service URLs:"
	@echo "  API: http://34.143.173.34:8081"
	@echo "  Docs: http://34.143.173.34:8081/docs"
	@echo "  Flower: http://34.143.173.34:5555"
	@echo ""
	@echo "📊 Check status:"
	@echo "  ssh -i $(ssh_key) $(u)@34.143.173.34 'cd /home/truong95k58/unified_api && docker compose -f docker-compose.server.yml ps'"
	@echo ""
	@echo "📋 View logs:"
	@echo "  ssh -i $(ssh_key) $(u)@34.143.173.34 'cd /home/truong95k58/unified_api && docker compose -f docker-compose.server.yml logs -f unified-api'"

deploy-prod:
	@echo "🚀 Deploying to PRODUCTION server..."
	@read -p "Enter production host: " host; \
	read -p "Enter remote directory: " dir; \
	make deploy h=$$host dir=$$dir && \
	make restart-app h=$$host dir=$$dir
	@echo "✓ Production deployment complete!"

start-all-remote:
	@echo "🚀 Starting ALL services on $(h)..."
	@echo "Step 1: Starting Docker services..."
	ssh -i $(ssh_key) $(u)@$(h) "cd $(dir) && docker compose -f docker-compose-full.yml up -d --build"
	@echo ""
	@echo "✓ All services started!"
	@echo ""
	@echo "🌐 Service URLs:"
	@echo "  API: http://$(h):8081"
	@echo "  Docs: http://$(h):8081/docs"
	@echo "  Flower: http://$(h):5555"
	@echo "  Qdrant: http://$(h):6333"
	@echo "  RabbitMQ: http://$(h):15672 (admin/admin123)"
	@echo ""
	@echo "📊 Check status:"
	@echo "  ssh -i $(ssh_key) $(u)@$(h) 'cd $(dir) && docker compose -f docker-compose-full.yml ps'"

start-all-local:
	@echo "🚀 Starting ALL services locally with docker-compose-full.yml"
	@echo ""
	@echo "Services include:"
	@echo "  - Unified API (with Zauba Direct Botasaurus)"
	@echo "  - Classifier Worker (async classification tasks)"
	@echo "  - Crawl Worker (async HS database/rulings search)"
	@echo "  - Report Worker (async Excel/TRAINS processing)"
	@echo "  - Flower (Celery Monitor for all workers)"
	@echo "  - Qdrant Vector DB"
	@echo "  - Redis"
	@echo "  - RabbitMQ"
	@echo "  - MinIO (Object Storage)"
	@echo ""
	docker compose -f docker-compose-full.yml up -d --build
	@echo ""
	@echo "✓ All services started!"
	@echo ""
	@echo "🌐 Service URLs:"
	@echo "  - API: http://localhost:8081"
	@echo "  - API Docs: http://localhost:8081/docs"
	@echo "  - Flower (Celery Monitor): http://localhost:5555"
	@echo "  - Qdrant: http://localhost:6333"
	@echo "  - MinIO Console: http://localhost:9001 (minioadmin/minioadmin123)"
	@echo "  - RabbitMQ: http://localhost:15672 (admin/admin123)"
	@echo ""
	@echo "🔧 Celery Workers:"
	@echo "  - classifier-worker: Classification tasks"
	@echo "  - crawl-worker: HS database/rulings search tasks"
	@echo "  - report-worker: Excel/TRAINS processing tasks"
	@echo ""
	@echo "📊 Check status:"
	@echo "  docker compose -f docker-compose-full.yml ps"
	@echo ""
	@echo "📋 View logs:"
	@echo "  docker compose -f docker-compose-full.yml logs -f unified-api"
	@echo "  docker compose -f docker-compose-full.yml logs -f classifier-worker"
	@echo "  docker compose -f docker-compose-full.yml logs -f crawl-worker"
	@echo "  docker compose -f docker-compose-full.yml logs -f report-worker"

sync-qdrant-from-remote:
	@echo "📥 Downloading Qdrant data from $(h)..."
	@if [ -d "./qdrant_data/collections" ] && [ -n "$$(ls -A ./qdrant_data/collections 2>/dev/null)" ]; then \
		read -p "⚠️  Local qdrant_data is not empty. Overwrite? (y/N): " confirm; \
		if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then \
			echo "❌ Sync cancelled."; \
			exit 1; \
		fi; \
	fi
	@mkdir -p qdrant_data
	rsync -avhzP --delete \
		-e "ssh -i $(ssh_key)" \
		$(u)@$(h):$(dir)/qdrant_data/ \
		./qdrant_data/
	@echo "✓ Qdrant data downloaded successfully!"
	@echo "  Collections synced to: ./qdrant_data/"
	@echo "  You can now run: make start-all-local"

sync-qdrant-to-remote:
	@echo "📤 Uploading Qdrant data to $(h)..."
	@if [ ! -d "./qdrant_data/collections" ] || [ -z "$$(ls -A ./qdrant_data/collections 2>/dev/null)" ]; then \
		echo "❌ Local qdrant_data is empty. Nothing to sync."; \
		exit 1; \
	fi
	ssh -i $(ssh_key) $(u)@$(h) "cd $(dir) && docker compose -f docker-compose-full.yml stop qdrant || docker compose -f docker-compose.server.yml stop qdrant || true"
	@echo "⏳ Waiting for Qdrant to stop..."
	@sleep 3
	rsync -avhzP --delete \
		-e "ssh -i $(ssh_key)" \
		./qdrant_data/ \
		$(u)@$(h):$(dir)/qdrant_data/
	ssh -i $(ssh_key) $(u)@$(h) "cd $(dir) && docker compose -f docker-compose-full.yml start qdrant || docker compose -f docker-compose.server.yml start qdrant || true"
	@echo "✓ Qdrant data uploaded successfully!"
	@echo "  Collections synced to: $(h):$(dir)/qdrant_data/"
