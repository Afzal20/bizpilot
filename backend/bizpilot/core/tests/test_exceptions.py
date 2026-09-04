from __future__ import annotations

from http import HTTPStatus

from rest_framework import exceptions
from rest_framework.test import APIRequestFactory

from bizpilot.core.exceptions import custom_exception_handler


def test_custom_exception_handler_validation_error():
    factory = APIRequestFactory()
    request = factory.post("/api/v1/test/")
    exc = exceptions.ValidationError({"email": ["Enter a valid email address."]})
    context = {"request": request}

    response = custom_exception_handler(exc, context)

    assert response is not None
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response["Content-Type"] == "application/problem+json"
    data = response.data
    assert data["status"] == HTTPStatus.BAD_REQUEST
    assert data["title"] == "Bad Request"
    assert "invalid_params" in data
    assert data["invalid_params"][0]["name"] == "email"
    assert data["invalid_params"][0]["reason"] == "Enter a valid email address."


def test_custom_exception_handler_not_found():
    factory = APIRequestFactory()
    request = factory.get("/api/v1/missing/")
    exc = exceptions.NotFound("Resource not found.")
    context = {"request": request}

    response = custom_exception_handler(exc, context)

    assert response is not None
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response["Content-Type"] == "application/problem+json"
    data = response.data
    assert data["status"] == HTTPStatus.NOT_FOUND
    assert data["title"] == "Not Found"
    assert data["detail"] == "Resource not found."
