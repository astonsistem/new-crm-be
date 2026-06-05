"""
ASIS API Session Manager
------------------------
Singleton yang mengelola token JWT ke ASIS API secara otomatis:
- Login saat token belum ada atau mendekati expired (buffer 5 menit)
- Retry otomatis sekali saat server mengembalikan HTTP 401
- Thread-safe via asyncio.Lock (double-checked locking)
- Support HTTP dan HTTPS, dengan atau tanpa port
"""

import asyncio
import time
from typing import Any, Optional

import httpx

from app.core.logging import get_logger

logger = get_logger("app.asis_session")

# Sesuaikan dengan ACCESS_TOKEN_EXPIRE_MINUTES di ASIS backend
_TOKEN_TTL = 720 * 60       # 12 jam dalam detik
_REFRESH_BUFFER = 5 * 60    # login ulang 5 menit sebelum expired


class AsisSession:
    def __init__(self) -> None:
        self._base_url: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None
        self._token: Optional[str] = None
        self._token_at: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    # ── Config ──────────────────────────────────────────────────────────────

    def configure(self, base_url: str, username: str, password: str) -> None:
        """Simpan kredensial dan invalidate token yang ada."""
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._token = None
        self._token_at = 0.0
        logger.info("AsisSession dikonfigurasi → %s (user: %s)", self._base_url, username)

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._username and self._password)

    # ── Token lifecycle ─────────────────────────────────────────────────────

    def _token_valid(self) -> bool:
        if not self._token:
            return False
        elapsed = time.monotonic() - self._token_at
        return elapsed < (_TOKEN_TTL - _REFRESH_BUFFER)

    async def _do_login(self) -> None:
        """Login ke ASIS dan simpan token. Harus dipanggil saat memegang lock."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/asis/auth/login",
                data={"username": self._username, "password": self._password},
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"ASIS login gagal: HTTP {resp.status_code} — {resp.text[:200]}"
            )
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_at = time.monotonic()
        logger.info("ASIS token berhasil diperbarui.")

    async def _ensure_token(self) -> None:
        """Pastikan token valid; re-login jika perlu (double-checked locking)."""
        if not self._token_valid():
            async with self._lock:
                # Cek ulang setelah mendapat lock — coroutine lain mungkin sudah login
                if not self._token_valid():
                    await self._do_login()

    # ── HTTP helpers ────────────────────────────────────────────────────────

    async def request(
        self,
        method: str,
        path: str,
        *,
        timeout: float = 60,
        **kwargs: Any,
    ) -> Any:
        """
        Kirim request ke ASIS API dengan token otomatis.
        Retry sekali jika server mengembalikan 401.
        """
        if not self.is_configured:
            raise RuntimeError(
                "AsisSession belum dikonfigurasi. "
                "Tambahkan konfigurasi ASIS melalui endpoint /asis-config terlebih dahulu."
            )

        await self._ensure_token()

        # Pastikan path dimulai dengan /
        if not path.startswith("/"):
            path = f"/{path}"

        async with httpx.AsyncClient(timeout=timeout) as client:
            headers = {"Authorization": f"Bearer {self._token}"}
            resp = await client.request(
                method, f"{self._base_url}{path}", headers=headers, **kwargs
            )

            # Token expired di sisi server → re-login sekali
            if resp.status_code == 401:
                logger.warning("ASIS 401 — token ditolak server, mencoba re-login…")
                async with self._lock:
                    self._token = None
                    await self._do_login()
                headers = {"Authorization": f"Bearer {self._token}"}
                resp = await client.request(
                    method, f"{self._base_url}{path}", headers=headers, **kwargs
                )

        resp.raise_for_status()
        return resp.json()

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> Any:
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        return await self.request("DELETE", path, **kwargs)

    # ── Status ──────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Kembalikan info status sesi untuk monitoring."""
        if not self.is_configured:
            return {"configured": False, "token_valid": False}
        elapsed = time.monotonic() - self._token_at if self._token_at else None
        remaining = max(0, _TOKEN_TTL - elapsed) if elapsed is not None else None
        return {
            "configured": True,
            "base_url": self._base_url,
            "username": self._username,
            "token_valid": self._token_valid(),
            "token_age_seconds": round(elapsed) if elapsed else None,
            "token_remaining_seconds": round(remaining) if remaining is not None else None,
        }


# ── Singleton ──────────────────────────────────────────────────────────────────
asis_session = AsisSession()
