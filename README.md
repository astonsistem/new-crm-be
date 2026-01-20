# CRM Backend

FastAPI-based backend for CRM system.

## Setup

1. Create virtual environment:
```bash
python -m venv venv
```

2. Activate virtual environment:
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file:
```bash
cp .env.example .env
```

5. Run the application:
```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --reload
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

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
