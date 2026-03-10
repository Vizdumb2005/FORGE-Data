# FORGE Data

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](./docker-compose.yml)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](./apps/api)
[![Next.js](https://img.shields.io/badge/next.js-15-000000?logo=next.js&logoColor=white)](./apps/web)

**FORGE Data** is an open-source, self-hosted data intelligence platform that combines the interactive spreadsheet experience of Quadratic AI with the conversational data analysis of Julius AI. Built for data analysts and scientists who want full control over their data and AI stack.

> **Bring Your Own Key (BYOK):** FORGE Data never stores your LLM API keys on external servers. All keys are encrypted at rest in your own database. Works with OpenAI, Anthropic, Google AI, Azure OpenAI, and local Ollama models.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser / Client                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │ :80
                     ┌──────▼──────┐
                     │    Nginx    │  Reverse Proxy
                     └──┬────┬─────┘
              /         │    │          /api/         /jupyter/
    ┌─────────▼──┐  ┌───▼────▼────┐  ┌──────────────┐
    │  Next.js   │  │   FastAPI   │  │   Jupyter     │
    │  Web App   │  │  REST + WS  │  │   Kernel GW   │
    │  :3000     │  │   :8000     │  │   :8888       │
    └────────────┘  └──────┬──────┘  └──────────────┘
                           │
          ┌────────────────┼───────────────────┐
          │                │                   │
   ┌──────▼──────┐  ┌──────▼──────┐  ┌────────▼────┐
   │  PostgreSQL │  │    Redis     │  │    MinIO    │
   │   :5432     │  │    :6379     │  │  :9000/9001 │
   └─────────────┘  └─────────────┘  └─────────────┘
                           │
                    ┌──────▼──────┐
                    │   MLflow    │
                    │   :5000     │
                    └─────────────┘
```

---

## Features

- **Interactive Data Grid** — Spreadsheet-like interface with live Python/SQL cell execution via Jupyter kernels
- **Conversational AI Analysis** — Chat with your data using any LLM provider (BYOK)
- **Multi-connector Support** — PostgreSQL, MySQL, BigQuery, Snowflake, CSV, Parquet, REST APIs
- **Experiment Tracking** — Integrated MLflow for model training runs and metrics
- **Notebook Export** — Export analyses as Jupyter notebooks or shareable reports
- **Version History** — Git-like versioning for data workbooks
- **Team Collaboration** — Share workbooks, datasets, and dashboards with your team
- **Self-Hosted & Private** — Your data never leaves your infrastructure
- **BYOK LLM Support** — OpenAI, Anthropic, Google AI, Azure OpenAI, Ollama (local)
- **Object Storage** — MinIO-backed file storage with S3-compatible API

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2+
- [Git](https://git-scm.com/)
- 8 GB RAM recommended (all services running)

### 1. Clone the repository

```bash
git clone https://github.com/your-org/forge-data.git
cd forge-data
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env to add your LLM API keys (optional — BYOK via UI also works)
```

### 3. Start the stack

```bash
make dev
```

This builds all images and starts every service. On first run, Docker pulls base images which may take a few minutes.

### 4. Initialize storage bucket

```bash
make minio-init
```

### 5. Run database migrations

```bash
make db-migrate
```

### 6. Open in your browser

| Service       | URL                          |
|--------------|------------------------------|
| FORGE App    | http://localhost             |
| API Docs     | http://localhost/api/docs    |
| Jupyter Lab  | http://localhost/jupyter/    |
| MLflow UI    | http://localhost:5000        |
| MinIO Console| http://localhost:9001        |

Default MinIO credentials: `forge` / `forgedata123`

---

## Development Commands

```bash
make dev           # Start full stack with hot-reload
make dev-down      # Stop all containers
make db-migrate    # Run pending Alembic migrations
make db-reset      # Wipe DB and re-run all migrations
make db-revision MSG="add users table"  # Generate new migration
make test-api      # Run pytest (API)
make test-web      # Run Next.js tests
make lint          # Run ruff + eslint with auto-fix
make logs          # Tail all container logs
make shell-api     # Shell into the API container
make shell-db      # psql into PostgreSQL
```

---

## Project Structure

```
forge-data/
├── apps/
│   ├── web/                  # Next.js 15 frontend (App Router)
│   └── api/                  # FastAPI Python backend
├── packages/
│   ├── db/                   # Alembic migrations & SQLAlchemy models
│   └── shared-types/         # Shared TypeScript type definitions
├── infra/
│   ├── docker/               # Dockerfiles + PostgreSQL init script
│   ├── k8s/                  # Kubernetes Helm chart
│   └── nginx/                # Nginx reverse proxy config
├── .github/
│   └── workflows/            # CI/CD pipelines
├── docker-compose.yml        # Local dev stack
├── docker-compose.prod.yml   # Production overrides
├── .env.example              # Documented environment variables
├── Makefile                  # Convenience commands
└── notebooks/                # Jupyter notebook workspace (gitignored)
```

---

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR.

- **Bug reports:** [Open an issue](https://github.com/your-org/forge-data/issues)
- **Feature requests:** Start a discussion before implementing
- **Security issues:** Email security@forge-data.dev (do not open public issues)

---

## License

FORGE Data is open-source software licensed under the [MIT License](./LICENSE).
