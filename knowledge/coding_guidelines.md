# Coding Guidelines and Best Practices

## Python Conventions
- Follow PEP 8 style formatting and PEP 484 type annotations.
- Use Pydantic models for request validation and environment configurations.
- Use asynchronous I/O (`httpx.AsyncClient`) for network requests to external services like Ollama and Qdrant.
- Keep dependencies lean and avoid heavyweight frameworks when lightweight alternatives suffice.

## API Design
- Adhere to RESTful resource naming conventions.
- Explicitly return appropriate HTTP status codes: 200 for success, 400/422 for client validation errors, 413 for oversized payloads, 404 for missing resources.
- Do not leak raw internal tracebacks to the client.

## Testing Strategy
- Unit tests should be self-contained and run isolated from live external servers by mocking HTTP clients or databases.
- Test edge cases thoroughly: empty inputs, maximum context boundaries, path traversal attacks, and idempotency in ingestion.
