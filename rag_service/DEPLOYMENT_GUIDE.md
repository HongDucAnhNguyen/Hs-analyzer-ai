# Deployment Guide - Smart HS Code Search AI

This guide explains how to deploy your application from your local machine to a remote server using the Makefile.

## Prerequisites

### On Local Machine:
- `rsync` installed
- SSH access to remote server
- Git repository initialized

### On Remote Server:
- Docker installed
- Docker Compose installed
- User has Docker permissions

## Quick Start

### 1. Configure SSH Key (3 Options)

**Option A: Pass as parameter (Recommended)**
```bash
make deploy SSH_KEY=~/.ssh/id_rsa
make deploy SSH_KEY=/path/to/your/private_key.pem
```

**Option B: Set environment variable**
```bash
# In your terminal (temporary)
export SSH_KEY=~/.ssh/id_rsa
make deploy

# Or in your ~/.bashrc or ~/.zshrc (permanent)
echo 'export SSH_KEY=~/.ssh/id_rsa' >> ~/.bashrc
source ~/.bashrc
```

**Option C: Use default SSH key**
```bash
# If you don't specify SSH_KEY, it uses your default SSH configuration
make deploy
```

### 2. Deploy from Local Machine

```bash
# Deploy code to remote server
make deploy SSH_KEY=~/.ssh/id_rsa

# Or deploy and automatically start
make deploy-start SSH_KEY=~/.ssh/id_rsa

# Or deploy and open SSH session
make deploy-ssh SSH_KEY=~/.ssh/id_rsa

# Without SSH key (uses default)
make deploy
```

### 3. Start Services on Remote Server

After deployment, SSH to your server:

```bash
ssh -i /path/to/private_key_file truong95k58@34.143.173.34
cd ~/smart-hs-code-search-ai
```

Then:

```bash
# Configure environment (first time only)
nano .env  # Add your API keys and configuration

# Start services
make start

# Check status
make status

# View logs
make logs
```

## Deployment Workflow

### Full Deployment Flow

```bash
# On LOCAL machine
┌─────────────────────────────────────────┐
│ 1. Make your code changes               │
│ 2. Test locally                         │
│ 3. Commit to git (optional)            │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ make deploy                             │
│ - Syncs files to remote                 │
│ - Excludes .git, .env, cache files     │
│ - Preserves gitignore rules            │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ SSH to remote server                    │
│ ssh -i key truong95k58@34.143.173.34  │
└─────────────────────────────────────────┘
                  ↓
# On REMOTE server
┌─────────────────────────────────────────┐
│ cd ~/smart-hs-code-search-ai           │
│ make start    (first time)              │
│ make rebuild  (if dependencies changed) │
└─────────────────────────────────────────┘
```

## Available Make Commands

### Local Machine Commands

```bash
# Deployment
make deploy              # Deploy code to remote server
make deploy-prod        # Same as deploy (production)
make deploy-ssh         # Deploy and open SSH session
make deploy-start       # Deploy and auto-start containers
make deploy-rebuild     # Deploy and auto-rebuild containers

# Help
make help               # Show all available commands
```

### Remote Server Commands

```bash
# Container Management
make start              # Start Docker containers
make stop               # Stop containers
make restart            # Restart containers
make rebuild            # Rebuild and restart (use after code changes)
make clean              # Stop and remove containers
make clean-all          # Stop, remove containers AND volumes (⚠️ deletes data)

# Monitoring
make logs               # View all container logs
make logs-api           # View API logs only
make logs-qdrant        # View Qdrant logs only
make status             # Show container status
make health             # Check API health

# Utilities
make shell              # Open bash shell in API container
make test-api           # Test API with sample request
make backup-qdrant      # Backup Qdrant vector data
make info               # Show deployment information
```

## Detailed Usage Examples

### Example 1: First Time Deployment

```bash
# 1. On local machine - deploy code
make deploy

# Output:
# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                    Deploying to Development Server                    ║
# ╚═══════════════════════════════════════════════════════════════════════╝
# 
# Branch:     feat/rag
# Deployer:   Your Name
# Time:       2025-12-01 10:30:00
# Remote:     truong95k58@34.143.173.34:~/smart-hs-code-search-ai
# 
# Syncing files...
# ✅ Deployment completed!

# 2. SSH to remote server
ssh -i /path/to/key truong95k58@34.143.173.34

# 3. Navigate to directory
cd ~/smart-hs-code-search-ai

# 4. Configure environment (FIRST TIME ONLY)
nano .env
# Add your API keys:
#   OPENAI_API_KEY=sk-...
#   COHERE_API_KEY=...
#   LOGFIRE_TOKEN=pylf_v1_...
#   etc.

# 5. Start services
make start

# 6. Check status
make status

# 7. View logs to verify
make logs-api
```

### Example 2: Update After Code Changes

```bash
# 1. On local machine - deploy updated code
make deploy

# 2. SSH to remote server
ssh -i /path/to/key truong95k58@34.143.173.34
cd ~/smart-hs-code-search-ai

# 3. Rebuild containers with new code
make rebuild

# This will:
# - Stop existing containers
# - Rebuild images with new code
# - Start containers
```

### Example 3: Quick Deploy and Start (Automated)

```bash
# Deploy and automatically start on remote (single command)
make deploy-start

# This does everything:
# - Syncs code to remote
# - SSHs to remote
# - Starts containers
```

### Example 4: Monitoring and Debugging

```bash
# SSH to server
ssh -i /path/to/key truong95k58@34.143.173.34
cd ~/smart-hs-code-search-ai

# Check what's running
make status

# View live logs
make logs-api

# Check API health
make health

# Open shell in container for debugging
make shell

# Test API endpoint
make test-api
```

## Configuration

### Remote Server Settings

Edit the `Makefile` to customize your deployment:

```makefile
# Remote server configuration
REMOTE_USER := truong95k58
REMOTE_HOST := 34.143.173.34
REMOTE_PATH := ~/smart-hs-code-search-ai
SSH_KEY := /path/to/your/private_key_file
```

### Environment Variables

On the **remote server**, ensure `.env` file has:

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8386
API_WORKERS=4
DEBUG=False

# Required API Keys
OPENAI_API_KEY=sk-your-actual-key
COHERE_API_KEY=your-cohere-key

# Database Connections
QDRANT_HOST=qdrant
QDRANT_PORT=6333
ES_URL=http://your-elasticsearch:9200
GRAPH_DB_URL=bolt://your-neo4j:7687
GRAPH_USER=neo4j
GRAPH_PASSWORD=your-password
DB_NAME=hscode

# Logfire (Optional but recommended)
LOGFIRE_TOKEN=pylf_v1_your-token
LOGFIRE_ENVIRONMENT=production
```

## What Gets Deployed

The `rsync` command syncs everything **except**:

- `.git/` - Git repository
- `.env`, `.env.local`, `.env.dev` - Environment files (create manually on server)
- `__pycache__/`, `*.pyc` - Python cache files
- `.venv/`, `venv/` - Virtual environments
- `node_modules/` - Node dependencies
- `qdrant_data/` - Vector database data (preserved on server)
- `.DS_Store` - macOS files
- Everything in `.gitignore`

**Included:**
- Source code (`src/`)
- Docker files (`Dockerfile`, `docker-compose.yml`)
- Requirements (`requirements.txt`)
- Configuration (`example.env`)
- Documentation (`*.md`)
- Scripts (`run.sh`, `Makefile`)
- Deployment metadata (`deployer` file)

## Troubleshooting

### Issue: rsync permission denied

```bash
# Make sure you have the correct SSH key
ssh -i /path/to/key truong95k58@34.143.173.34

# Test connection first
ssh -i /path/to/key truong95k58@34.143.173.34 "echo 'Connection successful'"
```

### Issue: Docker permission denied on remote

```bash
# SSH to remote server
ssh -i /path/to/key truong95k58@34.143.173.34

# Add user to docker group
sudo usermod -aG docker $USER

# Logout and login again
exit
ssh -i /path/to/key truong95k58@34.143.173.34
```

### Issue: Containers not starting

```bash
# SSH to remote
ssh -i /path/to/key truong95k58@34.143.173.34
cd ~/smart-hs-code-search-ai

# Check logs
make logs-api

# Verify .env file exists
ls -la .env

# Try rebuilding
make rebuild
```

### Issue: Port already in use

```bash
# SSH to remote
ssh -i /path/to/key truong95k58@34.143.173.34

# Check what's using the port
sudo lsof -i :8386

# Stop conflicting service or change port in .env
nano .env
# Change API_PORT=8387

# Restart
cd ~/smart-hs-code-search-ai
make restart
```

## Best Practices

### 1. Version Control

```bash
# Always commit before deploying
git add .
git commit -m "Your changes"
git push

# Then deploy
make deploy
```

### 2. Test Locally First

```bash
# Test locally before deploying
docker-compose up --build

# Test API
curl http://localhost:8386/health

# If working, deploy
make deploy
```

### 3. Backup Before Major Changes

```bash
# SSH to remote server
ssh -i /path/to/key truong95k58@34.143.173.34
cd ~/smart-hs-code-search-ai

# Backup Qdrant data
make backup-qdrant

# Now safe to deploy changes
```

### 4. Monitor After Deployment

```bash
# After deploying, always check logs
ssh -i /path/to/key truong95k58@34.143.173.34
cd ~/smart-hs-code-search-ai

# Monitor for errors
make logs-api

# Check health
make health
```

### 5. Use Automated Deployment for Speed

```bash
# For quick iterations
make deploy-rebuild

# This deploys and rebuilds in one command
```

## Comparison with PM2 Approach

| Aspect | PM2 (Your Coworker) | Docker (This Project) |
|--------|---------------------|----------------------|
| **Deployment** | `make deploy` | `make deploy` |
| **Start Service** | `make start` (PM2) | `make start` (Docker) |
| **Process Management** | PM2 manages Node.js | Docker manages containers |
| **Logs** | `pm2 logs` | `make logs` |
| **Restart** | `pm2 restart` | `make restart` |
| **Auto-restart** | PM2 built-in | Docker restart policy |
| **Environment** | Node.js | Any (Python, Node, etc.) |

The workflow is nearly identical!

## Quick Reference

```bash
# LOCAL MACHINE
make deploy              # Deploy code
make deploy-start       # Deploy and start
make deploy-rebuild     # Deploy and rebuild

# REMOTE SERVER (after SSH)
make start              # Start containers
make stop               # Stop containers
make restart            # Restart containers
make rebuild            # Rebuild and restart
make logs               # View logs
make status             # Check status
make health             # Test API
```

## Support

For issues:
1. Check logs: `make logs-api`
2. Check status: `make status`
3. View deployment info: `make info`
4. Check Docker: `docker ps`
5. Review documentation: `README.md`, `DOCKER_DEPLOYMENT.md`
