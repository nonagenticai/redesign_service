# Redesign Service -- Claude Code Instructions

## Overview

AI-powered website redesign microservice with screenshot rendering. Port 6306.

Part of the nonagenticai web_to_video microservice ecosystem. Follows the skill_builder/tts_service pattern.

## Architecture

- FastAPI + async PostgreSQL + Redis
- License token auth middleware
- Pydantic Settings configuration
- Docker + K8s deployment

## Key Files

| File | Purpose |
|------|---------|
| `src/asgi.py` | FastAPI app + lifespan |
| `src/config.py` | Pydantic Settings |
| `src/api/routes.py` | Domain API routes |
| `src/api/schemas.py` | Request/response models |
| `src/services/` | Business logic |
| `src/database/models.py` | SQLAlchemy ORM models |

## Testing

```bash
uv run pytest tests/ -v
```

## Code Style

- Python 3.12+, type hints on all functions
- Ruff for linting/formatting (100 char line length)
- Async/await throughout
- Pydantic models for all API schemas

## Before Completion

Before completing any plan or task, always run:

```bash
uv run ruff format .
uv run ruff check . --fix
uv run ty .
```
