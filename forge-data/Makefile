.PHONY: dev dev-down db-migrate db-reset test-api test-web logs shell-api lint \
        build clean minio-init setup-fast help

# ── Variables ─────────────────────────────────────────────────────────────────
COMPOSE        := docker compose
API_CONTAINER  := forge-data-api-1
WEB_CONTAINER  := forge-data-web-1

# ── Help ──────────────────────────────────────────────────────────────────────
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ───────────────────────────────────────────────────────────────
dev: ## Start the full local dev stack (builds images first)
	$(COMPOSE) up --build

setup-fast: ## One-command first-time setup (target: <15 minutes)
	@if [ ! -f .env ]; then cp .env.example .env; fi
	$(COMPOSE) up --build -d
	$(COMPOSE) exec api alembic -c /app/alembic.ini upgrade head
	docker run --rm --network forge-data_forge-net \
		-e MC_HOST_forge=http://forge:forgedata123@minio:9000 \
		minio/mc mb --ignore-existing forge/forge-data
	@echo "FORGE is ready: http://localhost"

dev-detach: ## Start the stack in detached mode
	$(COMPOSE) up --build -d

dev-down: ## Stop and remove all dev containers
	$(COMPOSE) down

# ── Database ──────────────────────────────────────────────────────────────────
db-migrate: ## Run Alembic migrations (alembic upgrade head) inside api container
	$(COMPOSE) exec api alembic -c /app/alembic.ini upgrade head

db-reset: ## Drop DB, recreate schemas, and run all migrations from scratch
	$(COMPOSE) exec postgres psql -U forge -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	$(COMPOSE) exec api alembic -c /app/alembic.ini upgrade head

db-revision: ## Generate a new Alembic migration (usage: make db-revision MSG="add users table")
	$(COMPOSE) exec api alembic -c /app/alembic.ini revision --autogenerate -m "$(MSG)"

# ── Testing ───────────────────────────────────────────────────────────────────
test-api: ## Run pytest inside the api container (warnings suppressed)
	$(COMPOSE) exec api python -W ignore::DeprecationWarning -m pytest tests/ -v --tb=short

test-web: ## Run Next.js tests inside the web container
	$(COMPOSE) exec web npm test -- --watchAll=false

test: test-api test-web ## Run all tests

# ── Linting ───────────────────────────────────────────────────────────────────
lint: ## Run ruff (api) and eslint (web)
	$(COMPOSE) exec api ruff check . --fix
	$(COMPOSE) exec api ruff format .
	$(COMPOSE) exec web npm run lint -- --fix

lint-check: ## Lint without auto-fix (useful for CI)
	$(COMPOSE) exec api ruff check .
	$(COMPOSE) exec web npm run lint

# ── Utilities ─────────────────────────────────────────────────────────────────
logs: ## Tail logs from all containers
	$(COMPOSE) logs -f

logs-api: ## Tail api container logs only
	$(COMPOSE) logs -f api

logs-web: ## Tail web container logs only
	$(COMPOSE) logs -f web

shell-api: ## Open a bash shell inside the api container
	$(COMPOSE) exec api bash

shell-web: ## Open a bash shell inside the web container
	$(COMPOSE) exec web sh

shell-db: ## Open psql inside the postgres container
	$(COMPOSE) exec postgres psql -U forge -d forge

# ── MinIO ─────────────────────────────────────────────────────────────────────
minio-init: ## Create the default MinIO bucket
	docker run --rm --network forge-data_forge-net \
		-e MC_HOST_forge=http://forge:forgedata123@minio:9000 \
		minio/mc mb --ignore-existing forge/forge-data

# ── Build & Clean ─────────────────────────────────────────────────────────────
build: ## Build all Docker images without starting
	$(COMPOSE) build

clean: ## Remove containers, volumes, and orphaned images
	$(COMPOSE) down -v --remove-orphans
	docker image prune -f
