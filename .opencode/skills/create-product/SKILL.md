---
name: create-product
description: Create the product.
license: MIT
compatibility: opencode
metadata:
  audience: developers
---

## What I do

- Build a REST API using FastAPI.
- All of the endpoints must provide a response in JSON format.
- The API has a public endpoint called `/products`. This endpoint returns the list of products.
- The API has a public endpoint called `/products/{id}`, where `{id}` represents the ID of the product to query. This endpoint returns the details of the product specified.
- The source code of the API must be stored in a file called `main.py`
- Every product has a unique id, a name, a description, a price and a photo url.
- The API must have an endpoint for updating an existing product: `PUT` `/products/{id}`. This endpoint requires authentication via a valid JSON Web Token. The ID of the product must not be updated.
- The API must have an endpoint for creating a new product: `POST` `/products/{id}`. This endpoint requires a valid JWT.
- The API must have an endpoint for deleting an existing product: `DELETE` `/products/{id}`. This endpoint requires a valid JWT.
- Products must be stored in a PostgreSQL database.
- Protect the API with CORS middleware.

- Use ruff as a linter.
- Create tests for the API and make sure the test coverage is greater than 90%.


## When to use me

Use this when you are creating the product from scratch.

