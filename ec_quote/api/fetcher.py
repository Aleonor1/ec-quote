"""Descarcarea atasamentelor trimise de CRM, cu garduri SSRF, si validarea continutului.

Reguli: numai https, numai gazde din lista din setari, fara IP literal, fara port
nestandard, redirect numai catre o gazda permisa, plafon de marime, timp limita,
tip stabilit din octetii magici (nu din extensie sau din MIME-ul declarat).
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import uuid
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

MAX_REDIRECTS = 3
SNIFF_BYTES = 2048

EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/tiff": ".tif",
    "application/pdf": ".pdf",
    "image/svg+xml": ".svg",
    "application/postscript": ".eps",
}

Resolver = Callable[[str], Awaitable[Sequence[str]]]


class AttachmentError(Exception):
    """code este stabil si ajunge in raspunsul API; message nu contine URL-ul."""

    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(code)
        self.code = code
        self.message = message
        self.status = status


def normalize_mime(value: str | None) -> str:
    return (value or "").split(";")[0].strip().lower()


def sniff_mime(head: bytes) -> str | None:
    """Tipul dupa octetii magici; None daca nu este unul cunoscut."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"%!PS"):
        return "application/postscript"
    text = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if text.startswith((b"<?xml", b"<svg", b"<!doctype svg", b"<!--")) and b"<svg" in text:
        return "image/svg+xml"
    return None


def check_content(head: bytes, allowed: Sequence[str]) -> str:
    mime = sniff_mime(head)
    if mime is None or mime not in allowed:
        raise AttachmentError("attachment_type_not_allowed", "Tipul fisierului nu este acceptat.", 415)
    return mime


def safe_filename(name: str | None) -> str | None:
    """Numele original, doar ca eticheta: fara cale, fara caractere de control, scurtat."""
    if not name:
        return None
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(ch for ch in base if ch.isprintable()).strip()
    return base[:120] or None


async def system_resolver(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


class AttachmentFetcher:
    def __init__(self, *, client: httpx.AsyncClient, allowed_hosts: Sequence[str],
                 allowed_mimes: Sequence[str], max_bytes: int, timeout_seconds: float,
                 resolver: Resolver = system_resolver):
        self._client = client
        self._hosts = {h.lower().rstrip(".") for h in allowed_hosts}
        self._mimes = tuple(allowed_mimes)
        self._max_bytes = max_bytes
        self._timeout = timeout_seconds
        self._resolver = resolver

    def _check_url(self, url: str, *, redirect: bool) -> str:
        code = "attachment_redirect_blocked" if redirect else "attachment_host_not_allowed"
        blocked = AttachmentError(code, "Adresa atasamentului nu este permisa.")
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            raise blocked from None
        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme != "https" or not host or parts.username or parts.password:
            raise blocked
        if port not in (None, 443):
            raise blocked
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise blocked
        if host not in self._hosts:
            raise blocked
        return host

    async def _check_resolution(self, host: str) -> None:
        # Aparare in adancime: o gazda permisa nu are voie sa indice spre reteaua interna.
        try:
            addresses = await self._resolver(host)
        except OSError:
            raise AttachmentError("attachment_fetch_failed", "Atasamentul nu a putut fi descarcat.", 502) from None
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise AttachmentError("attachment_host_not_allowed", "Adresa atasamentului nu este permisa.")

    async def fetch(self, url: str, declared_mime: str, dest_dir: Path) -> tuple[Path, str]:
        """Descarca in dest_dir si intoarce (cale, mime stabilit din continut)."""
        if normalize_mime(declared_mime) not in self._mimes:
            raise AttachmentError("attachment_type_not_allowed", "Tipul fisierului nu este acceptat.", 415)
        self._check_url(url, redirect=False)
        try:
            # Plafon pe toata descarcarea, peste timpii pe operatie ai clientului.
            async with asyncio.timeout(self._timeout * 2):
                return await self._download(url, dest_dir)
        except (httpx.HTTPError, TimeoutError):
            raise AttachmentError("attachment_fetch_failed", "Atasamentul nu a putut fi descarcat.", 502) from None

    async def _download(self, url: str, dest_dir: Path) -> tuple[Path, str]:
        too_large = AttachmentError("attachment_too_large", "Fisierul depaseste marimea maxima.", 413)
        for hop in range(MAX_REDIRECTS + 1):
            host = self._check_url(url, redirect=hop > 0)
            await self._check_resolution(host)
            async with self._client.stream("GET", url, follow_redirects=False,
                                           timeout=self._timeout) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code != 200:
                    raise AttachmentError("attachment_fetch_failed", "Atasamentul nu a putut fi descarcat.", 502)
                length = response.headers.get("content-length", "")
                if length.isdigit() and int(length) > self._max_bytes:
                    raise too_large
                dest_dir.mkdir(parents=True, exist_ok=True)
                tmp = dest_dir / f".{uuid.uuid4().hex}.part"
                size = 0
                head = b""
                try:
                    with tmp.open("wb") as out:
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > self._max_bytes:
                                raise too_large
                            if len(head) < SNIFF_BYTES:
                                head += chunk[:SNIFF_BYTES - len(head)]
                            out.write(chunk)
                    mime = check_content(head, self._mimes)
                    final = dest_dir / f"{uuid.uuid4().hex}{EXTENSIONS.get(mime, '.bin')}"
                    os.replace(tmp, final)
                    return final, mime
                finally:
                    tmp.unlink(missing_ok=True)
        raise AttachmentError("attachment_redirect_blocked", "Prea multe redirectari.")
