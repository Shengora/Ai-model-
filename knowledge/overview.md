# Project Overview

Welcome to the internal engineering architecture guide.

## System Components
1. **API Gateway**: Handles incoming HTTP requests and routes them to microservices.
2. **Worker Pool**: Asynchronous background jobs processed via Celery and Redis.
3. **Storage Engine**: PostgreSQL for relational structured data, and S3-compatible MinIO for blobs.

## Coding Conventions
- All services run Python 3.12 with async FastAPI.
- Code should be strictly typed using Pydantic models.
- Tests are written in pytest and run with `pytest tests/`.
