import os

TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/products_test"
if os.environ.get("DATABASE_URL", TEST_DATABASE_URL) != TEST_DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is set to a non-test database; refusing to run the test suite against it"
    )
os.environ["JWT_SECRET"] = os.environ.get("JWT_SECRET", "test-secret-8d0e4a6f2b9c1d7ec1a2b3c4d5e6f7a8")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import psycopg  # noqa: E402
import pytest  # noqa: E402

from main import SCHEMA_DDL, SEED_PRODUCTS  # noqa: E402

ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
TEST_DB = "products_test"


@pytest.fixture(scope="session", autouse=True)
def ensure_database():
    try:
        conn = psycopg.connect(ADMIN_URL, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone() is None:
        conn.execute(f"CREATE DATABASE {TEST_DB}")
    conn.close()
    yield
    try:
        conn = psycopg.connect(ADMIN_URL, autocommit=True)
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        conn.close()
    except psycopg.errors.ObjectInUse:
        pass


@pytest.fixture(scope="session")
def client(ensure_database):
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_db(ensure_database):
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    try:
        conn.execute(SCHEMA_DDL)
        conn.execute("TRUNCATE products")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO products (id, name, description, price, photo_url) VALUES (%s, %s, %s, %s, %s)",
                [
                    (p["id"], p["name"], p["description"], p["price"], p["photo_url"])
                    for p in SEED_PRODUCTS
                ],
            )
    finally:
        conn.close()