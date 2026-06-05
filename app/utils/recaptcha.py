from httpx import AsyncClient
from app.config import get_settings

settings = get_settings()

async def verify_recaptcha(token: str) -> bool:
    """
    Verify reCAPTCHA token with Google's API
    """
    async with AsyncClient() as client:
        response = await client.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": settings.recaptcha_secret_key,
                "response": token
            }
        )
        result = response.json()
        return result.get("success", False)