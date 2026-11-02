SHELL := /bin/bash

# Remote server configuration
REMOTE_USER := truong95k58
REMOTE_HOST := 34.143.173.34
REMOTE_PATH := ~/smart-hs-code-search-ai

# SSH key can be passed as parameter: make deploy SSH_KEY=~/.ssh/id_rsa
# Or set default in your shell: export SSH_KEY=~/.ssh/id_rsa
SSH_KEY ?=

# SSH command with optional key
SSH_CMD = ssh $(if $(SSH_KEY),-i $(SSH_KEY),)

# Docker compose command wrapper - auto-detects v1 or v2
define run_compose
	@if command -v docker-compose >/dev/null 2>&1; then \
		docker-compose $(1); \
	elif docker compose version >/dev/null 2>&1; then \
		docker compose $(1); \
	else \
		echo "❌ Error: Docker Compose not found!"; \
		echo "Install: https://docs.docker.com/compose/install/"; \
		exit 1; \
	fi
endef

.PHONY: help deploy deploy-prod start stop restart logs status clean build

help:
	@echo "╔═══════════════════════════════════════════════════════════════════════╗"
	@echo "║         Smart HS Code Search AI - Deployment Commands                ║"
	@echo "╚═══════════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Usage with SSH key:"
	@echo "  make deploy SSH_KEY=~/.ssh/id_rsa"
	@echo "  make deploy SSH_KEY=/path/to/key.pem"
	@echo ""
	@echo "Or set environment variable:"
	@echo "  export SSH_KEY=~/.ssh/id_rsa"
	@echo "  make deploy"
	@echo ""
	@echo "Local commands:"
	@echo "  make deploy          - Deploy code to remote server"
	@echo "  make deploy-prod     - Deploy code to remote server (production)"
	@echo "  make deploy-ssh      - Deploy and open SSH session"
	@echo "  make deploy-start    - Deploy and start containers"
	@echo "  make deploy-rebuild  - Deploy and rebuild containers"
	@echo ""
	@echo "Remote commands (run these after SSH to server):"
	@echo "  make start           - Start Docker containers"
	@echo "  make stop            - Stop Docker containers"
	@echo "  make restart         - Restart Docker containers"
	@echo "  make rebuild         - Rebuild and restart containers"
	@echo "  make logs            - View container logs"
	@echo "  make status          - Check container status"
	@echo "  make clean           - Stop and remove containers"
	@echo ""

# ============================================================================
# DEPLOYMENT COMMANDS (Run from local machine)
# ============================================================================

deploy:
	@echo "╔═══════════════════════════════════════════════════════════════════════╗"
	@echo "║                    Deploying to Development Server                    ║"
	@echo "╚═══════════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Branch:     $$(git rev-parse --abbrev-ref HEAD)"
	@echo "Deployer:   $$(git config user.name)"
	@echo "Time:       $$(date '+%Y-%m-%d %H:%M:%S')"
	@echo "Remote:     $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_PATH)"
	@echo ""
	@echo "Creating deployment metadata..."
	@echo "Deploying from branch: $$(git rev-parse --abbrev-ref HEAD) by $$(git config user.name) at $$(date '+%Y-%m-%d %H:%M:%S')" > deployer
	@echo "Commit: $$(git rev-parse HEAD)" >> deployer
	@echo ""
	@echo "Syncing files..."
	rsync -avhzL --delete \
		--no-perms --no-owner --no-group \
		--exclude .git \
		--exclude .env \
		--exclude .env.local \
		--exclude .env.dev \
		--exclude __pycache__ \
		--exclude *.pyc \
		--exclude .pytest_cache \
		--exclude .venv \
		--exclude venv \
		--exclude node_modules \
		--exclude qdrant_data \
		--exclude .DS_Store \
		--include deployer \
		--filter=":- .gitignore" \
		$(if $(SSH_KEY),-e "ssh -i $(SSH_KEY)",) \
		. $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_PATH)
	@echo ""
	@echo "✅ Deployment completed!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. SSH to server: $(SSH_CMD) $(REMOTE_USER)@$(REMOTE_HOST)"
	@echo "  2. Go to directory: cd $(REMOTE_PATH)"
	@echo "  3. Configure .env file (if needed): nano .env"
	@echo "  4. Start services: make start"
	@echo ""

deploy-prod: deploy

# Deploy and automatically open SSH session
deploy-ssh:
	@$(MAKE) deploy SSH_KEY="$(SSH_KEY)"
	@echo "Opening SSH session to remote server..."
	$(SSH_CMD) -t $(REMOTE_USER)@$(REMOTE_HOST) "cd $(REMOTE_PATH) ; bash --login"

# Deploy and start containers (fully automated)
deploy-start:
	@$(MAKE) deploy SSH_KEY="$(SSH_KEY)"
	@echo ""
	@echo "Starting containers on remote server..."
	$(SSH_CMD) $(REMOTE_USER)@$(REMOTE_HOST) "cd $(REMOTE_PATH) && make start"

# Deploy and rebuild containers (fully automated)
deploy-rebuild:
	@$(MAKE) deploy SSH_KEY="$(SSH_KEY)"
	@echo ""
	@echo "Rebuilding containers on remote server..."
	$(SSH_CMD) $(REMOTE_USER)@$(REMOTE_HOST) "cd $(REMOTE_PATH) && make rebuild"

# ============================================================================
# REMOTE SERVER COMMANDS (Run on remote server after SSH)
# ============================================================================

start:
	@echo "╔═══════════════════════════════════════════════════════════════════════╗"
	@echo "║                        Starting Docker Containers                     ║"
	@echo "╚═══════════════════════════════════════════════════════════════════════╝"
	@echo ""
	@if [ ! -f .env ]; then \
		echo "⚠️  WARNING: .env file not found!"; \
		echo "Creating .env from example.env..."; \
		cp example.env .env; \
		echo ""; \
		echo "⚠️  Please edit .env with your actual configuration:"; \
		echo "   nano .env"; \
		echo ""; \
		read -p "Press Enter to continue or Ctrl+C to exit..."; \
	fi
	@echo "Starting containers..."
	@if command -v docker-compose >/dev/null 2>&1; then \
		docker-compose up -d; \
	elif docker compose version >/dev/null 2>&1; then \
		docker compose up -d; \
	else \
		echo "❌ Error: Neither 'docker-compose' nor 'docker compose' found!"; \
		echo "Please install Docker Compose:"; \
		echo "  https://docs.docker.com/compose/install/"; \
		exit 1; \
	fi
	@echo ""
	@echo "✅ Containers started!"
	@echo ""
	@echo "View logs: make logs"
	@echo "Check status: make status"
	@echo ""

stop:
	@echo "Stopping containers..."
	$(call run_compose,stop)
	@echo "✅ Containers stopped"

restart:
	@echo "Restarting containers..."
	$(call run_compose,restart)
	@echo "✅ Containers restarted"

rebuild:
	@echo "╔═══════════════════════════════════════════════════════════════════════╗"
	@echo "║                       Rebuilding Docker Containers                    ║"
	@echo "╚═══════════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Stopping existing containers..."
	$(call run_compose,down)
	@echo ""
	@echo "Building new images..."
	$(call run_compose,build --no-cache)
	@echo ""
	@echo "Starting containers..."
	$(call run_compose,up -d)
	@echo ""
	@echo "✅ Rebuild completed!"
	@echo ""

logs:
	@echo "Showing logs (Ctrl+C to exit)..."
	$(call run_compose,logs -f)

logs-api:
	@echo "Showing API logs (Ctrl+C to exit)..."
	$(call run_compose,logs -f api)

logs-qdrant:
	@echo "Showing Qdrant logs (Ctrl+C to exit)..."
	$(call run_compose,logs -f qdrant)

status:
	@echo "╔═══════════════════════════════════════════════════════════════════════╗"
	@echo "║                          Container Status                             ║"
	@echo "╚═══════════════════════════════════════════════════════════════════════╝"
	@echo ""
	$(call run_compose,ps)
	@echo ""
	@if [ -f .env ]; then \
		echo "Environment: $$(grep LOGFIRE_ENVIRONMENT .env | cut -d= -f2)"; \
		echo "API Port: $$(grep API_PORT .env | cut -d= -f2)"; \
	fi
	@echo ""

health:
	@echo "Checking API health..."
	@PORT=$$(grep API_PORT .env 2>/dev/null | cut -d= -f2 || echo "8386"); \
	curl -s http://localhost:$$PORT/health | python3 -m json.tool || echo "❌ API not responding"

clean:
	@echo "⚠️  WARNING: This will stop and remove all containers"
	@read -p "Continue? (y/N): " -n 1 -r; \
	echo ""; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "Removing containers..."; \
		$$(call run_compose,down); \
		echo "✅ Containers removed"; \
	else \
		echo "Cancelled"; \
	fi

clean-all:
	@echo "⚠️  WARNING: This will DELETE all containers AND data (including Qdrant vectors)!"
	@read -p "Are you sure? Type 'yes' to continue: " -r; \
	echo ""; \
	if [[ $$REPLY == "yes" ]]; then \
		echo "Removing containers and volumes..."; \
		$$(call run_compose,down -v); \
		echo "✅ Containers and volumes removed"; \
	else \
		echo "Cancelled"; \
	fi

# ============================================================================
# UTILITY COMMANDS
# ============================================================================

build:
	@echo "Building Docker images..."
	$(call run_compose,build)

pull:
	@echo "Pulling latest images..."
	$(call run_compose,pull)

update:
	@echo "Updating application..."
	git pull
	$(call run_compose,up --build -d)
	@echo "✅ Update completed"

backup-qdrant:
	@echo "Backing up Qdrant data..."
	@BACKUP_FILE="qdrant_backup_$$(date +%Y%m%d_%H%M%S).tar.gz"; \
	tar -czf $$BACKUP_FILE ./qdrant_data; \
	echo "✅ Backup created: $$BACKUP_FILE"

shell:
	@echo "Opening shell in API container..."
	$(call run_compose,exec api bash)

test-api:
	@echo "Testing API endpoint..."
	@PORT=$$(grep API_PORT .env 2>/dev/null | cut -d= -f2 || echo "8386"); \
	curl -X 'POST' "http://localhost:$$PORT/api/v1/search/hscode" \
		-H 'accept: application/json' \
		-H 'Content-Type: multipart/form-data' \
		-F 'product_name=smartphone'

# Show deployment info
info:
	@if [ -f deployer ]; then \
		echo "╔═══════════════════════════════════════════════════════════════════════╗"; \
		echo "║                       Deployment Information                          ║"; \
		echo "╚═══════════════════════════════════════════════════════════════════════╝"; \
		echo ""; \
		cat deployer; \
		echo ""; \
	else \
		echo "No deployment information found"; \
	fi
