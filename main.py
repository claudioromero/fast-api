import asyncio
import os
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Any, cast

import jwt
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, BeforeValidator, Field, HttpUrl, field_serializer

JWT_SECRET = os.environ.get("JWT_SECRET")
if JWT_SECRET is None:
    raise RuntimeError("JWT_SECRET environment variable must be set")

JWT_ALGORITHM = "HS256"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/products")
SEED_DATABASE = os.environ.get("SEED_DATABASE", "").lower() in {"1", "true", "yes"}
CORS_ORIGINS = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "*").split(",") if origin.strip()]
CORS_ALLOW_CREDENTIALS = os.environ.get("CORS_ALLOW_CREDENTIALS", "").lower() in {"1", "true", "yes"}

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price NUMERIC(12, 2) NOT NULL,
    photo_url TEXT NOT NULL DEFAULT ''
)
"""

SEED_PRODUCTS = [
    {
        "id": 1,
        "name": "Laptop",
        "description": "A high-performance laptop for work and play.",
        "price": "999.99",
        "photo_url": "https://example.com/photos/laptop.jpg",
    },
    {
        "id": 2,
        "name": "Mouse",
        "description": "A comfortable wireless mouse with precision tracking.",
        "price": "29.99",
        "photo_url": "https://example.com/photos/mouse.jpg",
    },
    {
        "id": 3,
        "name": "Keyboard",
        "description": "A mechanical keyboard with backlit keys.",
        "price": "79.99",
        "photo_url": "https://example.com/photos/keyboard.jpg",
    },
    {
        "id": 4,
        "name": "Monitor",
        "description": "A 27-inch 4K monitor with vivid colors.",
        "price": "299.99",
        "photo_url": "https://example.com/photos/monitor.jpg",
    },
    {
        "id": 5,
        "name": "Headphones",
        "description": "Noise-cancelling over-ear headphones.",
        "price": "149.99",
        "photo_url": "https://example.com/photos/headphones.jpg",
    },
]

security = HTTPBearer(auto_error=False)

pool: AsyncConnectionPool | None = None
pool_lock = asyncio.Lock()


class Product(BaseModel):
    id: int
    name: str
    description: str = ""
    price: Decimal
    photo_url: str = ""

    @field_serializer("price")
    def _serialize_price(self, value: Decimal) -> float:
        return float(value)


def _empty_url_to_none(value: object) -> object:
    return None if value == "" else value


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    price: Decimal = Field(ge=0, decimal_places=2)
    photo_url: Annotated[HttpUrl | None, BeforeValidator(_empty_url_to_none)] = None


class ProductUpdate(BaseModel):
    id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    photo_url: Annotated[HttpUrl | None, BeforeValidator(_empty_url_to_none)] = None


PRODUCT_COLUMNS = ", ".join(Product.model_fields)


def _url_to_db(value: HttpUrl | None) -> str:
    return str(value) if value else ""


async def fetch_one(pool: AsyncConnectionPool, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    async with pool.connection() as conn:
        row = await (await conn.execute(sql, params)).fetchone()
        return cast(dict[str, Any] | None, row)


async def mutate_one(pool: AsyncConnectionPool, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    async with pool.connection() as conn:
        row = await (await conn.execute(sql, params)).fetchone()
        await conn.commit()
        return cast(dict[str, Any] | None, row)


async def init_database(p: AsyncConnectionPool) -> None:
    async with p.connection() as conn:
        await conn.execute(SCHEMA_DDL)
        if SEED_DATABASE:
            for product in SEED_PRODUCTS:
                await conn.execute(
                    "INSERT INTO products (id, name, description, price, photo_url)"
                    " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                    (
                        product["id"],
                        product["name"],
                        product["description"],
                        product["price"],
                        product["photo_url"],
                    ),
                )
        await conn.commit()


async def get_pool() -> AsyncConnectionPool:
    global pool
    if pool is None:
        async with pool_lock:
            if pool is None:
                candidate = AsyncConnectionPool(DATABASE_URL, open=False, kwargs={"row_factory": dict_row})
                try:
                    await candidate.open()
                    await init_database(candidate)
                except BaseException:
                    await candidate.close()
                    raise
                pool = candidate
    return pool


async def get_pool_dependency() -> AsyncConnectionPool:
    return await get_pool()


def require_auth(credentials: HTTPAuthorizationCredentials | None = Security(security)) -> None:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"], "verify_iat": True},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


@asynccontextmanager
async def lifespan(_: FastAPI):
    await get_pool()
    yield
    if pool is not None:
        await pool.close()


app = FastAPI(lifespan=lifespan, title="Products API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/products", response_model=list[Product])
async def get_products(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _pool: AsyncConnectionPool = Depends(get_pool_dependency),
):
    async with _pool.connection() as conn:
        return await (await conn.execute(
            f"SELECT {PRODUCT_COLUMNS} FROM products ORDER BY id LIMIT %s OFFSET %s",
            (limit, offset),
        )).fetchall()


@app.get("/products/{product_id}", response_model=Product)
async def get_product(
    product_id: Annotated[int, Path(ge=1)],
    _pool: AsyncConnectionPool = Depends(get_pool_dependency),
):
    row = await fetch_one(
        _pool,
        f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = %s",
        (product_id,),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return row


@app.put("/products/{product_id}", response_model=Product)
async def update_product(
    product_id: Annotated[int, Path(ge=1)],
    update: ProductUpdate,
    _: None = Depends(require_auth),
    _pool: AsyncConnectionPool = Depends(get_pool_dependency),
):
    data = update.model_dump(exclude_unset=True, exclude_none=True)
    provided_id = data.pop("id", None)
    if provided_id is not None and provided_id != product_id:
        raise HTTPException(status_code=422, detail="Product id cannot be changed")
    if "photo_url" in data:
        data["photo_url"] = str(data["photo_url"])
    if data:
        assignments = ", ".join(f"{column} = %s" for column in data)
        row = await mutate_one(
            _pool,
            f"UPDATE products SET {assignments} WHERE id = %s RETURNING {PRODUCT_COLUMNS}",
            (*data.values(), product_id),
        )
    else:
        row = await fetch_one(
            _pool,
            f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = %s",
            (product_id,),
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return row


@app.post("/products/{product_id}", status_code=201, response_model=Product)
async def create_product(
    product_id: Annotated[int, Path(ge=1)],
    product_data: ProductCreate,
    response: Response,
    _: None = Depends(require_auth),
    _pool: AsyncConnectionPool = Depends(get_pool_dependency),
):
    values = product_data.model_dump()
    photo_url = _url_to_db(values["photo_url"])
    try:
        row = await mutate_one(
            _pool,
            "INSERT INTO products (id, name, description, price, photo_url)"
            f" VALUES (%s, %s, %s, %s, %s) RETURNING {PRODUCT_COLUMNS}",
            (product_id, values["name"], values["description"], values["price"], photo_url),
        )
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Product already exists") from None
    response.headers["Location"] = f"/products/{product_id}"
    return row


@app.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: Annotated[int, Path(ge=1)],
    _: None = Depends(require_auth),
    _pool: AsyncConnectionPool = Depends(get_pool_dependency),
):
    row = await mutate_one(
        _pool,
        "DELETE FROM products WHERE id = %s RETURNING id",
        (product_id,),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return None