# fast-api

A REST API for managing products, built with FastAPI, async PostgreSQL (`psycopg`), and JWT authentication.

All endpoints return JSON responses.

## Requirements

- Python 3.14+
- PostgreSQL (running locally)

## Installation

```bash
uv sync
```

## Configuration

The API is configured through environment variables:

| Variable              | Required | Default                                            | Description                          |
| --------------------- | -------- | -------------------------------------------------- | ------------------------------------ |
| `JWT_SECRET`          | yes      | —                                                  | HMAC secret used to sign/verify JWTs |
| `DATABASE_URL`        | no       | `postgresql://postgres:postgres@localhost:5432/products` | PostgreSQL connection URL     |
| `SEED_DATABASE`       | no       | `false`                                            | Seed the `products` table on startup (set to `true` to enable) |
| `CORS_ORIGINS`        | no       | `*`                                                | Comma-separated list of allowed CORS origins |
| `CORS_ALLOW_CREDENTIALS` | no    | `false`                                            | Allow credentials in CORS requests  |

`JWT_SECRET` is mandatory; the app refuses to start without it.

CORS is enabled via middleware. The default (`CORS_ORIGINS=*`) allows requests from any origin without credentials. If you enable `CORS_ALLOW_CREDENTIALS=true`, browsers require explicit origins, so set `CORS_ORIGINS` to your frontend origin(s) (e.g. `https://app.example.com,http://localhost:3000`).

The `products` table is created automatically on startup (`CREATE TABLE IF NOT EXISTS`).

## Running the server

```bash
uv run fast-api        # runs uvicorn on 0.0.0.0:8000
```

or directly:

```bash
uv run uvicorn main:app --reload
```

Interactive API docs: http://localhost:8000/docs

## Authentication

The `POST`, `PUT`, and `DELETE` endpoints require a valid JWT in the `Authorization` header:

```
Authorization: Bearer <token>
```

Tokens are verified with HS256 and must contain these claims:

- `sub` — the user identifier
- `iat` — issued-at timestamp
- `exp` — expiry timestamp

Example token creation:

```bash
uv run python -c "
import jwt, time
print(jwt.encode({'sub': 'demo', 'iat': int(time.time()), 'exp': int(time.time()) + 3600}, JWT_SECRET, algorithm='HS256'))
"
```

## API

### GET `/products`

Returns the list of products.

Query parameters:

| Parameter | Default | Constraints       |
| --------- | ------- | ----------------- |
| `limit`   | `50`    | 1–100             |
| `offset`  | `0`     | ≥ 0               |

### GET `/products/{id}`

Returns the product with the given ID (404 if not found).

### POST `/products/{id}` — requires JWT

Creates a new product with the given ID (409 if the ID already exists).

Request body:

| Field         | Type    | Required |
| ------------- | ------- | -------- |
| `name`        | string  | yes      |
| `description` | string  | no       |
| `price`       | number  | yes      |
| `photo_url`   | string  | no       |

Constraints: `name` is 1–100 characters, `description` up to 500, `price` up to 2 decimal places. `photo_url`, when provided (and non-empty), must be a valid HTTP(S) URL. Product IDs must be positive integers.

Returns `201` with the created product and a `Location` header.

### PUT `/products/{id}` — requires JWT

Updates an existing product (404 if not found). Any subset of fields may be provided; explicit `null` values are ignored.

Request body:

| Field         | Type   | Required |
| ------------- | ------ | -------- |
| `name`        | string | no       |
| `description` | string | no       |
| `price`       | number | no       |
| `photo_url`   | string | no       |

The product ID is immutable: it always comes from the URL. If the body includes an `id` that differs from the URL ID, the request is rejected with `422`.

Returns `200` with the updated product.

### DELETE `/products/{id}` — requires JWT

Deletes the product with the given ID (404 if not found). Returns `204` with no body.

### Error responses

- `401` — missing or invalid JWT
- `404` — product not found
- `409` — product with that ID already exists
- `422` — invalid request body

## Tests

The test suite runs against a dedicated PostgreSQL database (`products_test`) created and dropped automatically. Requires access to a `postgres` superuser database (override with `POSTGRES_ADMIN_URL`).

```bash
uv run pytest
```

## Linting & type checking

```bash
uv run ruff check .
uv run mypy main.py tests
```