# Redesign Service

AI-powered website redesign microservice with screenshot rendering

Part of the nonagenticai web_to_video microservice ecosystem.

## Quick Start

```bash
# Install dependencies
uv sync

# Copy environment config
cp .env.example .env

# Start infrastructure
docker compose up -d

# Run the service
uv run python -m src.asgi

# Or use the entry point
uv run redesign-service
```

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest tests/ -v

# Type check
uv run ty check .

# Lint
uv run ruff check .
uv run ruff format .
```

## Docker

```bash
# Development
docker compose up -d

# Production
docker compose -f docker-compose.production.yml up -d
```

## API

- Health: `GET /health`
- Docs: `GET /docs`
- API: `/api/v1/redesign`

## Port: 6306

## License

Apache 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

## Licensing

This service contains no licence enforcement of its own and runs no licence
server. It runs with no licence switch set; unset means off.
