# FORGE Data: Open-Source Data Intelligence Platform for AI Analytics

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](./docker-compose.yml)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](./apps/api)
[![Next.js](https://img.shields.io/badge/next.js-15-000000?logo=next.js&logoColor=white)](./apps/web)

**FORGE Data** is an open-source, self-hosted data intelligence platform for interactive analytics, AI-assisted data exploration, and modern data workflows. It combines a spreadsheet-style interface with conversational AI analysis, built for data analysts, data scientists, and engineering teams that need full control over their data and AI stack.

If you're looking for a private alternative to cloud BI tools, AI data copilots, and notebook-heavy analytics stacks, FORGE Data gives you a unified self-hosted workspace for SQL, Python, dashboards, and LLM-powered analysis.

> **Bring Your Own Key (BYOK):** FORGE Data never stores your LLM API keys on external servers. All keys are encrypted at rest in your own database. Works with OpenAI, Anthropic, Google AI, Azure OpenAI, and local Ollama models.

## Why FORGE Data

FORGE Data helps teams run secure, self-hosted analytics with AI: connect data sources, query with SQL and Python, and collaborate in one private workspace. It is designed for organizations that need modern AI analytics without sending sensitive data to third-party SaaS platforms.

### Best for

- Self-hosted business intelligence and private analytics platforms
- AI-assisted data analysis with BYOK LLM providers
- Data science and analytics teams needing SQL + Python in one interface
- Engineering teams building governed internal data tools

## Table of Contents

- [Platform Architecture](#platform-architecture)
- [Key Features for Data Analytics and AI Workflows](#key-features-for-data-analytics-and-ai-workflows)
- [Quick Start: Run FORGE Data Locally with Docker](#quick-start-run-forge-data-locally-with-docker)
- [Development Commands](#development-commands)
- [Self-Hosting FORGE Data](#self-hosting-forge-data)
- [Repository Structure](#repository-structure)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## Platform Architecture

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

## Key Features for Data Analytics and AI Workflows

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

## Quick Start: Run FORGE Data Locally with Docker

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2+
- [Git](https://git-scm.com/)
- 8 GB RAM recommended (all services running)

### 1. Clone the repository

```bash
git clone https://github.com/Vizdumb2005/FORGE-Data.git
cd FORGE-Data
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

## Self-Hosting FORGE Data

### Docker Compose (Recommended for single server)

```bash
git clone https://github.com/Vizdumb2005/FORGE-Data.git
cd FORGE-Data
cp .env.example .env
# Edit .env with your values (JWT_SECRET, strong DB password, etc.)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
# Visit http://your-server-ip
```

### Kubernetes (Helm)

```bash
helm install forge-data ./infra/k8s --namespace forge --create-namespace -f infra/k8s/values.prod.yaml
```

### System Requirements

- Minimum: 4 CPU cores, 8GB RAM, 50GB disk
- Recommended: 8 CPU, 16GB RAM, 200GB SSD
- For ML workloads: GPU support via Jupyter GPU image override

### BYOK (Bring Your Own Key)

FORGE never stores or sends your LLM API keys to any third party.
Keys are encrypted at rest using AES-256 (Fernet) with a key derived from your JWT_SECRET.
All inference happens directly from your server to the LLM provider.

---

## Repository Structure

```
FORGE-Data/
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

## FAQ

### What is FORGE Data?

FORGE Data is an open-source data intelligence platform for self-hosted analytics, combining SQL, Python, and LLM-powered analysis in a collaborative web interface.

### Is FORGE Data self-hosted?

Yes. FORGE Data is built for self-hosting with Docker Compose and Kubernetes support.

### Which AI providers are supported?

FORGE Data supports OpenAI, Anthropic, Google AI, Azure OpenAI, and local Ollama models with BYOK.

### Can I use FORGE Data for private or regulated data?

Yes. FORGE Data is designed for privacy-focused deployments where data and keys stay in your infrastructure.

---

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR.

- **Bug reports:** [Open an issue](https://github.com/Vizdumb2005/FORGE-Data/issues)
- **Feature requests:** Start a discussion before implementing
- **Security issues:** Email security@forge-data.dev (do not open public issues)

---

## License

FORGE Data is open-source software licensed under the [MIT License](./LICENSE).
