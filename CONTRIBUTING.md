# Contributing to FORGE Data

Thank you for your interest in contributing to FORGE Data! This document covers everything you need to know to get started.

---

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating you agree to uphold these standards. Report unacceptable behavior to the maintainers.

---

## Running Locally

### Prerequisites

- Docker and Docker Compose v2+
- Node.js 20+ (for local frontend work outside Docker)
- Python 3.11+ (for local backend work outside Docker)
- Git

### Setup

```bash
# 1. Fork and clone the repository
git clone https://github.com/<your-username>/forge-data.git
cd forge-data

# 2. Copy and configure environment
cp .env.example .env
# Add any LLM keys you want to test with

# 3. Start the full stack
make dev

# 4. Initialize resources
make minio-init
make db-migrate
```

The app will be available at http://localhost.

### Running services individually (without Docker)

**API (FastAPI):**
```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Web (Next.js):**
```bash
cd apps/web
npm install
npm run dev
```

---

## Branch Naming Convention

All branches should follow this pattern:

| Prefix    | Purpose                                  | Example                          |
|-----------|------------------------------------------|----------------------------------|
| `feature/`| New features or enhancements             | `feature/csv-connector`          |
| `fix/`    | Bug fixes                                | `fix/jupyter-kernel-timeout`     |
| `chore/`  | Maintenance, deps, CI, docs, refactoring | `chore/upgrade-next-15`          |
| `release/`| Release preparation                      | `release/v0.2.0`                 |

---

## Pull Request Checklist

Before opening a PR, ensure all of the following are true:

- [ ] **Branch** follows the naming convention above
- [ ] **Commit messages** are clear and in the imperative mood ("Add CSV connector" not "Added CSV connector")
- [ ] **Tests pass** — `make test` succeeds locally
- [ ] **Linting passes** — `make lint-check` produces no errors
- [ ] **Migrations** — if you changed DB models, a new Alembic migration file is included
- [ ] **TypeScript** — no new `any` types without justification in a comment
- [ ] **Secrets** — no API keys, passwords, or tokens are committed (check `.env` is gitignored)
- [ ] **Documentation** — README or inline docs updated if behavior/config changed
- [ ] **Breaking changes** — clearly noted in the PR description
- [ ] **Small PRs** — prefer focused, reviewable changes over massive PRs

---

## Adding a New Data Connector

FORGE Data uses a connector plugin architecture. Here's how to add support for a new data source:

### 1. Create the connector module

```bash
# Create a new file in the connectors directory
apps/api/connectors/<connector_name>.py
```

Implement the `BaseConnector` interface:

```python
# apps/api/connectors/base.py defines:
class BaseConnector:
    async def test_connection(self) -> bool: ...
    async def get_schema(self) -> list[TableSchema]: ...
    async def execute_query(self, sql: str) -> QueryResult: ...
    async def fetch_sample(self, table: str, n: int = 100) -> QueryResult: ...
```

### 2. Register the connector

Add your connector to `apps/api/connectors/__init__.py`:

```python
from .my_connector import MyConnector

CONNECTOR_REGISTRY = {
    ...
    "my_connector": MyConnector,
}
```

### 3. Add connection form fields

Add the fields schema in `packages/shared-types/src/connectors.ts` so the frontend can render the connection form automatically.

### 4. Add an integration test

Create `apps/api/tests/connectors/test_my_connector.py`. Use the `docker-compose.yml` service or a mock for the external system.

### 5. Document it

Add a row to the connector table in `README.md` and create a short doc file at `docs/connectors/<name>.md`.

---

## Project Structure Quick Reference

```
apps/api/
├── main.py              # FastAPI app entry point
├── routers/             # Route handlers (one file per domain)
├── services/            # Business logic layer
├── connectors/          # Data source connectors
├── models/              # Pydantic request/response models
├── db/                  # SQLAlchemy ORM models
└── tests/               # pytest test suite

apps/web/
├── app/                 # Next.js App Router pages
├── components/          # Reusable React components
├── lib/                 # API client, utilities
└── hooks/               # Custom React hooks
```

---

## Getting Help

- Open a [GitHub Discussion](https://github.com/your-org/forge-data/discussions) for questions
- Open an [Issue](https://github.com/your-org/forge-data/issues) for bugs
- PRs are always welcome, even for documentation fixes
