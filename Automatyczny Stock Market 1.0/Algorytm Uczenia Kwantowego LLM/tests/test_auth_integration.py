"""Integration tests for authentication flow."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import json

from src.main import app
from src.infrastructure.database.session import get_db_session
from src.domain.entities.user import UserRole


@pytest.mark.asyncio
async def test_registration_flow():
    """Test complete registration flow from frontend to database."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Test registration endpoint
        registration_data = {
            "username": "testuser123",
            "email": "test123@example.com",
            "password": "TestPassword123!"
        }
        
        response = await client.post("/api/v2/users/register", json=registration_data)
        assert response.status_code == 201
        
        user_data = response.json()
        assert user_data["email"] == registration_data["email"]
        assert user_data["username"] == registration_data["username"]
        assert user_data["role"] == UserRole.USER.value
        assert user_data["is_active"] is True


@pytest.mark.asyncio
async def test_login_flow():
    """Test complete login flow from frontend to backend."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # First register a user
        registration_data = {
            "username": "logintest123",
            "email": "logintest123@example.com",
            "password": "TestPassword123!"
        }
        
        reg_response = await client.post("/api/v2/users/register", json=registration_data)
        assert reg_response.status_code == 201
        
        # Test login endpoint
        login_data = {
            "email": registration_data["email"],
            "password": registration_data["password"]
        }
        
        response = await client.post("/api/v2/users/login", json=login_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == registration_data["email"]
        
        # Test accessing protected endpoint with token
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        me_response = await client.get("/api/v2/users/me", headers=headers)
        assert me_response.status_code == 200
        
        me_data = me_response.json()
        assert me_data["email"] == registration_data["email"]


@pytest.mark.asyncio
async def test_login_page_renders():
    """Test that login page renders correctly."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/login")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Zaloguj się" in response.text
        assert "dark" in response.text  # Check for dark theme


@pytest.mark.asyncio
async def test_register_page_renders():
    """Test that register page renders correctly."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/register")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Stwórz konto" in response.text
        assert "dark" in response.text  # Check for dark theme


@pytest.mark.asyncio
async def test_invalid_login():
    """Test login with invalid credentials."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        login_data = {
            "email": "nonexistent@example.com",
            "password": "WrongPassword123!"
        }
        
        response = await client.post("/api/v2/users/login", json=login_data)
        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_duplicate_registration():
    """Test registration with existing email."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        registration_data = {
            "username": "duplicate123",
            "email": "duplicate123@example.com",
            "password": "TestPassword123!"
        }
        
        # First registration should succeed
        response1 = await client.post("/api/v2/users/register", json=registration_data)
        assert response1.status_code == 201
        
        # Second registration with same email should fail
        registration_data["username"] = "different456"
        response2 = await client.post("/api/v2/users/register", json=registration_data)
        assert response2.status_code == 400


@pytest.mark.asyncio
async def test_password_validation():
    """Test password strength validation."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Test weak password
        registration_data = {
            "username": "weakpass123",
            "email": "weakpass123@example.com",
            "password": "weak"  # Too short
        }
        
        response = await client.post("/api/v2/users/register", json=registration_data)
        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_logout_flow():
    """Test logout functionality."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register and login
        registration_data = {
            "username": "logouttest123",
            "email": "logouttest123@example.com",
            "password": "TestPassword123!"
        }
        
        await client.post("/api/v2/users/register", json=registration_data)
        
        login_response = await client.post("/api/v2/users/login", json={
            "email": registration_data["email"],
            "password": registration_data["password"]
        })
        
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test logout
        logout_response = await client.post("/api/v2/users/logout", headers=headers)
        assert logout_response.status_code == 200
        
        # Token should no longer work
        me_response = await client.get("/api/v2/users/me", headers=headers)
        assert me_response.status_code == 401


# Run tests with: pytest tests/test_auth_integration.py -v
