from datetime import UTC, datetime, timedelta

import jwt

from main import JWT_ALGORITHM, JWT_SECRET


def auth_headers(token_lifetime: timedelta = timedelta(hours=1), **claims):
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "test-user",
            "iat": now,
            "exp": now + token_lifetime,
            **claims,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


def test_get_products_returns_json_list(client):
    response = client.get("/products")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    products = response.json()
    assert isinstance(products, list)
    assert len(products) == 5


def test_get_products_return_cors_headers(client):
    response = client.get("/products", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


def test_cors_preflight_allows_write_methods(client):
    response = client.options(
        "/products/1",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"
    assert "PUT" in response.headers.get("access-control-allow-methods", "")


def test_get_products_supports_pagination(client):
    products = client.get("/products", params={"limit": 2, "offset": 1}).json()
    assert [p["id"] for p in products] == [2, 3]
    assert client.get("/products", params={"limit": 1000}).status_code == 422
    assert client.get("/products", params={"offset": -1}).status_code == 422


def test_get_products_include_all_fields(client):
    products = client.get("/products").json()
    assert set(products[0]) == {"id", "name", "description", "price", "photo_url"}


def test_get_product_by_id(client):
    response = client.get("/products/1")
    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "name": "Laptop",
        "description": "A high-performance laptop for work and play.",
        "price": 999.99,
        "photo_url": "https://example.com/photos/laptop.jpg",
    }


def test_get_product_not_found(client):
    response = client.get("/products/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found"}


def test_create_product_requires_token(client):
    body = {"name": "Webcam", "price": 49.99}
    assert client.post("/products/6", json=body).status_code == 401
    assert client.post("/products/6", json=body, headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_create_product_rejects_token_without_required_claims(client):
    token = jwt.encode({"sub": "test-user"}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    body = {"name": "Webcam", "price": 49.99}
    response = client.post("/products/6", json=body, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_create_product_rejects_expired_token(client):
    body = {"name": "Webcam", "price": 49.99}
    response = client.post(
        "/products/6",
        json=body,
        headers=auth_headers(token_lifetime=timedelta(hours=-1)),
    )
    assert response.status_code == 401


def test_create_product(client):
    headers = auth_headers()
    response = client.post(
        "/products/6",
        json={"name": "Webcam", "description": "HD", "price": 49.99, "photo_url": "https://example.com/webcam.jpg"},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["location"] == "/products/6"
    assert response.json()["id"] == 6
    assert client.get("/products/6").json()["name"] == "Webcam"


def test_create_product_validates_body(client):
    response = client.post("/products/6", json={"name": "", "price": "not-a-number"}, headers=auth_headers())
    assert response.status_code == 422


def test_create_product_rejects_excess_price_precision(client):
    response = client.post("/products/6", json={"name": "Webcam", "price": 1.999}, headers=auth_headers())
    assert response.status_code == 422


def test_create_product_rejects_invalid_photo_url(client):
    response = client.post(
        "/products/6",
        json={"name": "Webcam", "price": 10, "photo_url": "not-a-url"},
        headers=auth_headers(),
    )
    assert response.status_code == 422


def test_create_product_allows_empty_photo_url(client):
    response = client.post(
        "/products/6",
        json={"name": "Webcam", "price": 10, "photo_url": ""},
        headers=auth_headers(),
    )
    assert response.status_code == 201
    assert response.json()["photo_url"] == ""


def test_create_product_rejects_oversized_name(client):
    response = client.post("/products/6", json={"name": "a" * 101, "price": 10}, headers=auth_headers())
    assert response.status_code == 422


def test_update_product_photo_url_is_validated(client):
    response = client.put("/products/1", json={"photo_url": "https://example.com/new.jpg"}, headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["photo_url"] == "https://example.com/new.jpg"
    assert client.put("/products/1", json={"photo_url": "not-a-url"}, headers=auth_headers()).status_code == 422


def test_update_product_rejects_excess_price_precision(client):
    response = client.put("/products/1", json={"price": 1.999}, headers=auth_headers())
    assert response.status_code == 422


def test_routes_reject_non_positive_ids(client):
    headers = auth_headers()
    assert client.get("/products/0").status_code == 422
    assert client.get("/products/-1").status_code == 422
    assert client.post("/products/0", json={"name": "X", "price": 1}, headers=headers).status_code == 422
    assert client.put("/products/0", json={"name": "X"}, headers=headers).status_code == 422
    assert client.delete("/products/0", headers=headers).status_code == 422


def test_create_duplicate_product_conflicts(client):
    headers = auth_headers()
    body = {"name": "Webcam", "price": 49.99}
    assert client.post("/products/6", json=body, headers=headers).status_code == 201
    assert client.post("/products/6", json=body, headers=headers).status_code == 409


def test_update_product_requires_token(client):
    assert client.put("/products/1", json={"name": "Pro Laptop"}).status_code == 401
    assert (
        client.put("/products/1", json={"name": "Pro Laptop"}, headers={"Authorization": "Bearer bad"}).status_code
        == 401
    )


def test_update_product(client):
    response = client.put("/products/1", json={"name": "Pro Laptop", "price": 899.99}, headers=auth_headers())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["name"] == "Pro Laptop"
    assert response.json()["price"] == 899.99
    assert client.get("/products/1").json()["name"] == "Pro Laptop"


def test_update_product_with_empty_body(client):
    response = client.put("/products/1", json={}, headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["name"] == "Laptop"


def test_update_product_cannot_change_id(client):
    response = client.put("/products/1", json={"id": 999, "name": "Ghost"}, headers=auth_headers())
    assert response.status_code == 422
    assert client.get("/products/1").status_code == 200
    assert client.get("/products/999").status_code == 404


def test_update_product_keeps_id_from_path(client):
    response = client.put("/products/1", json={"id": 1, "name": "Renamed"}, headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["name"] == "Renamed"


def test_update_product_ignores_null_fields(client):
    response = client.put("/products/1", json={"name": None, "price": None}, headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["name"] == "Laptop"
    assert response.json()["price"] == 999.99


def test_update_product_not_found(client):
    response = client.put("/products/999", json={"name": "Ghost"}, headers=auth_headers())
    assert response.status_code == 404


def test_delete_product_requires_token(client):
    assert client.delete("/products/1").status_code == 401


def test_delete_product(client):
    response = client.delete("/products/1", headers=auth_headers())
    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/products/1").status_code == 404


def test_delete_product_not_found(client):
    assert client.delete("/products/999", headers=auth_headers()).status_code == 404