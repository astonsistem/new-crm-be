# CRM Backend API

FastAPI-based backend for CRM system with JWT authentication and role-based access control.

## Features

- JWT Authentication (Access Token + Refresh Token)
- Role-Based Access Control (RBAC)
- Customer roles: Level 1, 2, and 3
- PostgreSQL database
- SQLAlchemy ORM
- Password hashing with bcrypt

## Setup

### 1. Create virtual environment:
```bash
python -m venv venv
```

### 2. Activate virtual environment:
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Install dependencies:
```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Create `.env` file from example:
```bash
cp .env.example .env
```

Edit `.env` with your configuration:
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/crm_db
SECRET_KEY=your-super-secret-key-change-this-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### 5. Setup PostgreSQL Database

Create the database:
```sql
CREATE DATABASE crm_db;
```

### 6. Initialize Database

Run the initialization script to create tables and seed data:
```bash
python init_db.py
```

This creates:
- All database tables
- 5 roles: Admin, Sales, Customer Level 1, 2, and 3
- Default admin user (username: `admin`, password: `admin123`)

**⚠️ Important:** Change admin password after first login!

### 7. Run the Application

```bash
python main.py
```

Or with uvicorn:
```bash
uvicorn main:app --reload
```

API available at: `http://localhost:8000`

## API Documentation

Interactive documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Authentication Endpoints

### Login
```http
POST /auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "admin123"
}
```

Response:
```json
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "eyJ0eXAi...",
  "token_type": "bearer"
}
```

### Refresh Access Token
```http
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "your_refresh_token"
}
```

### Logout
```http
POST /auth/logout
Content-Type: application/json

{
  "refresh_token": "your_refresh_token"
}
```

## Using Protected Endpoints

Include access token in Authorization header:
```
Authorization: Bearer <access_token>
```

## Roles

1. **Admin** - Full system access
2. **Sales** - Sales team member
3. **Customer Level 1** - Basic customer access
4. **Customer Level 2** - Intermediate customer access
5. **Customer Level 3** - Advanced customer access

## Project Structure

```
CRM BE/
├── app/
│   ├── __init__.py
│   ├── config.py          # Configuration settings
│   ├── models/            # Database models
│   ├── schemas/           # Pydantic schemas
│   └── routers/           # API routes
├── venv/                  # Virtual environment
├── main.py               # Application entry point
├── requirements.txt      # Python dependencies
├── .env.example         # Environment variables template
├── .gitignore           # Git ignore file
└── README.md            # This file
```

## Development

- API runs on: http://localhost:8000
- Auto-reload enabled in development mode
- Check `/health` endpoint for service status
