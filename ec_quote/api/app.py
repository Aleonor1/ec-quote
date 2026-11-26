"""Aplicatia FastAPI a ec-quote: un API neutru fata de canal.

- CRM-ul trimite mesajele WhatsApp la POST /v1/inbound si livreaza actiunile din raspuns;
- widgetul de pe site vorbeste cu /v1/chat/* pe baza unui token de sesiune semnat;
- in mod umbra, omul aproba din CRM prin /v1/approvals/{id}/approve;
- extensia Chrome de pe WhatsApp Web cere sugestii la /v1/assist/* (un om insereaza si trimite).

Toate dependintele sunt injectate in create_app; adaptoarele reale se construiesc in main.py.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import os
import re
import secrets
import time
import traceback
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from ec_quote.api.fetcher import (
    EXTENSIONS,
    SNIFF_BYTES,
    AttachmentError,
    AttachmentFetcher,
    Resolver,
    check_content,
    safe_filename,
    sniff_mime,
    system_resolver,
)
from ec_quote.api.logutil import contact_ref, logger, request_id_var
from ec_quote.api.ratelimit import KeyedLocks, RateLimiter
from ec_quote.api.schemas import (
    ASSIST_KEY_PATTERN,
    ASSIST_MAX_MESSAGES,
    ASSIST_MAX_TEXT,
    SITE_KEY_PATTERN,
    ApprovalRequest,
    AssistPaymentLinkRequest,
    AssistSuggestRequest,
    ChatMessageRequest,
    ChatSessionRequest,
    InboundRequest,
    action_for_crm,
    action_for_site,
    suggestion_payload,
)
from ec_quote.api.security import Signer, TokenError, secrets_equal
from ec_quote.api.store import ApiStore
from ec_quote.config import Settings
from ec_quote.contracts import (
    AssistEngine,
    AssistMessage,
    AssistSuggestion,
    Attachment,
    Contact,
    Engine,
    InboundMessage,
    OutboundAction,
)

STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_PATHS = ("/v1/chat/upload", "/v1/assist/upload")
SUGGEST_PATH = "/v1/assist/suggest"
JSON_BODY_LIMIT = 256 * 1024
SUGGEST_BODY_LIMIT = 2 * 1024 * 1024  # conversatia vizibila, citita de extensie
MULTIPART_OVERHEAD = 64 * 1024
MEDIA_MIMES = ("image/png", "image/jpeg", "image/webp")
APPROVAL_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
MESSAGE_ID = re.compile(r"[\x21-\x7e]{1,200}")
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")

_ACTIONS = TypeAdapter(list[OutboundAction])

HTTP_CODES = {404: "not_found", 405: "method_not_allowed", 400: "bad_request", 413: "body_too_large"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers


class BodyTooLarge(Exception):
    pass


def error_body(code: str, message: str, **extra) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id_var.get(), **extra}}


def _error_response(status: int, code: str, message: str, headers=None, **extra) -> JSONResponse:
    return JSONResponse(error_body(code, message, **extra), status_code=status, headers=headers)


class RequestContextMiddleware:
    """Id de cerere, plafon pe corpul cererii, o linie de log pe cerere, 500 uniform fara detalii."""

    def __init__(self, app, *, upload_limit: int, monotonic: Callable[[], float]):
        self.app = app
        self.upload_limit = upload_limit
        self.monotonic = monotonic

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        path = scope["path"]
        limit = (self.upload_limit if path in UPLOAD_PATHS
                 else SUGGEST_BODY_LIMIT if path == SUGGEST_PATH else JSON_BODY_LIMIT)
        state = {"status": 0, "received": 0}

        async def limited_receive():
            message = await receive()
            if message["type"] == "http.request":
                state["received"] += len(message.get("body", b""))
                if state["received"] > limit:
                    scope["ecq_body_too_large"] = True  # FastAPI poate inveli exceptia intr-un 400
                    raise BodyTooLarge
            return message

        async def tagged_send(message):
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                message["headers"] = [*message.get("headers", []),
                                      (b"x-request-id", rid.encode()),
                                      (b"x-content-type-options", b"nosniff")]
            await send(message)

        started = self.monotonic()
        try:
            length = headers.get(b"content-length", b"")
            if length.isdigit() and int(length) > limit:
                raise BodyTooLarge
            await self.app(scope, limited_receive, tagged_send)
        except Exception as exc:
            too_large = isinstance(exc, BodyTooLarge)
            if not too_large:
                # Doar tipul si locul: mesajul exceptiei si sursa pot contine date ale clientului.
                frames = " < ".join(f"{Path(f.filename).name}:{f.lineno} {f.name}"
                                    for f in reversed(traceback.extract_tb(exc.__traceback__)[-8:]))
                logger.error("unhandled error type=%s at %s", type(exc).__name__, frames)
            if not state["status"]:
                response = (_error_response(413, "body_too_large", "Cererea este prea mare.") if too_large
                            else _error_response(500, "internal_error", "Eroare interna."))
                await response(scope, receive, tagged_send)
        finally:
            route = scope.get("route")
            logger.info("request method=%s route=%s status=%s ms=%d", scope["method"],
                        getattr(route, "path", "unmatched"), state["status"],
                        (self.monotonic() - started) * 1000)
            request_id_var.reset(token)


def create_app(
    engine: Engine,
    settings: Settings,
    *,
    clock: Callable[[], datetime],
    assist: AssistEngine | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    http_client: httpx.AsyncClient | None = None,
    resolver: Resolver = system_resolver,
    store: ApiStore | None = None,
) -> FastAPI:
    """clock intoarce ora curenta cu fus orar (Europe/Bucharest in productie).

    assist: motorul modului asistat. Daca lipseste si `engine` are `suggest` si
    `create_payment_link`, se foloseste el; altfel rutele de sugestie raspund 503.
    """
    assist_engine = assist
    if assist_engine is None and all(callable(getattr(engine, name, None))
                                     for name in ("suggest", "create_payment_link")):
        assist_engine = engine
    assist_tokens = [(name, token.get_secret_value()) for name, token in settings.assist_tokens]
    upload_key = settings.signing_key("assist-upload")
    data_root = settings.data_dir.resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    db = store or ApiStore(data_root / "api.sqlite3", clock=lambda: clock().timestamp())
    inbound_secret = settings.inbound_secret.get_secret_value()
    session_signer = Signer(settings.signing_key("chat-session"))
    media_signer = Signer(settings.signing_key("media"))
    log_salt = settings.signing_key("log-ref")
    locks = KeyedLocks()
    clients: dict[str, httpx.AsyncClient] = {}

    limit_sessions = RateLimiter(settings.rate_sessions_per_ip_per_hour, 3600, monotonic)
    limit_ip = RateLimiter(settings.rate_messages_per_ip_per_minute, 60, monotonic)
    limit_session = RateLimiter(settings.rate_messages_per_session_per_minute, 60, monotonic)
    limit_uploads = RateLimiter(settings.rate_uploads_per_session_per_hour, 3600, monotonic)
    limit_polls = RateLimiter(settings.rate_polls_per_session_per_minute, 60, monotonic)
    limit_assist = RateLimiter(settings.rate_assist_per_token_per_minute, 60, monotonic)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        for client in clients.values():
            await client.aclose()
        if store is None:
            db.close()

    app = FastAPI(title="ec-quote", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware,
                       upload_limit=settings.max_upload_bytes + MULTIPART_OVERHEAD, monotonic=monotonic)
    # CORS este stratul exterior, ca si erorile sa poarte antetele pentru originile permise.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-EcQuote-Session"],
        expose_headers=["X-Request-ID", "Retry-After"],
        allow_credentials=False,
        max_age=600,
    )

    # ---------- erori ----------

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return _error_response(exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(AttachmentError)
    async def _attachment_error(_: Request, exc: AttachmentError):
        return _error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(BodyTooLarge)
    async def _too_large(_: Request, __: BodyTooLarge):
        return _error_response(413, "body_too_large", "Cererea este prea mare.")

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError):
        # Numai campul si tipul erorii; valoarea primita nu se intoarce.
        fields = [{"field": ".".join(str(p) for p in e.get("loc", ())), "issue": e.get("type", "invalid")}
                  for e in exc.errors()]
        return _error_response(422, "invalid_request", "Cerere invalida.", fields=fields)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        if request.scope.get("ecq_body_too_large"):
            return _error_response(413, "body_too_large", "Cererea este prea mare.")
        code = HTTP_CODES.get(exc.status_code, "http_error")
        return _error_response(exc.status_code, code, "Cererea nu a putut fi procesata.")

    # ---------- ajutoare ----------

    def now_ts() -> float:
        return clock().timestamp()

    def require_secret(request: Request) -> None:
        if not secrets_equal(request.headers.get("x-ecquote-secret"), inbound_secret):
            raise ApiError(401, "unauthorized", "Secret lipsa sau gresit.")

    def client_ip(request: Request) -> str:
        """IP-ul clientului pentru limitele de ritm. Verifica si accesul la rutele de chat."""
        via_proxy = secrets_equal(request.headers.get("x-ecquote-secret"), inbound_secret)
        if settings.chat_require_secret and not via_proxy:
            raise ApiError(401, "unauthorized", "Secret lipsa sau gresit.")
        forwarded = request.headers.get("x-ecquote-client-ip", "").strip()
        if via_proxy and forwarded:
            return forwarded[:64]  # App Proxy-ul calculatorului spune cine este vizitatorul
        hops = settings.trusted_proxy_hops
        if hops:
            chain = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
            if len(chain) >= hops:
                return chain[-hops]
        return request.client.host if request.client else "unknown"

    def check_rate(limiter: RateLimiter, key: str) -> None:
        retry = limiter.hit(key)
        if retry is not None:
            raise ApiError(429, "rate_limited", "Prea multe cereri. Încercați din nou în scurt timp.",
                           {"Retry-After": str(max(1, math.ceil(retry)))})

    def session(request: Request) -> Contact:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        alternate = request.headers.get("x-ecquote-session")  # pentru proxy-uri care scot Authorization
        if alternate:
            scheme, token = "bearer", alternate
        try:
            if scheme.lower() != "bearer":
                raise TokenError("invalid")
            payload = session_signer.verify(token.strip(), now_ts())
            sid = payload.get("sid")
            if not isinstance(sid, str) or not re.fullmatch(SITE_KEY_PATTERN, sid):
                raise TokenError("invalid")
        except TokenError as exc:
            code = "session_expired" if exc.reason == "expired" else "session_invalid"
            raise ApiError(401, code, "Sesiunea nu este valida.") from None
        source = payload.get("src")
        return Contact(channel="site", key=sid, ad_source=source if isinstance(source, str) else None)

    def media_url_for(request: Request) -> Callable[[str], str]:
        base = settings.public_base_url or str(request.base_url).rstrip("/")

        def make(image_path: str) -> str:
            path = Path(image_path)
            resolved = (path if path.is_absolute() else Path.cwd() / path).resolve()
            if not resolved.is_relative_to(data_root) or not resolved.is_file():
                # Motorul trebuie sa scrie imaginile sub directorul de date; altfel nu le expunem.
                logger.error("media outside data dir or missing")
                raise ApiError(500, "internal_error", "Eroare interna.")
            rel = resolved.relative_to(data_root).as_posix()
            token = media_signer.sign({"p": rel}, now_ts() + settings.media_url_ttl_seconds)
            return f"{base}/v1/media/{token}"

        return make

    def conversation_dir(contact: Contact) -> Path:
        return data_root / "conversations" / contact.channel / contact.key / "inbound"

    async def save_upload(upload: UploadFile, dest: Path) -> tuple[Path, str]:
        """Scrie fisierul incarcat cu plafon de marime; tipul vine din octetii magici."""
        dest.mkdir(parents=True, exist_ok=True)
        tmp = dest / f".{uuid.uuid4().hex}.part"
        size, head = 0, b""
        try:
            with tmp.open("wb") as out:
                while chunk := await upload.read(64 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise ApiError(413, "upload_too_large", "Fișierul depășește mărimea maximă.")
                    if len(head) < SNIFF_BYTES:
                        head += chunk[:SNIFF_BYTES - len(head)]
                    out.write(chunk)
            mime = check_content(head, settings.allowed_mimes)
            final = dest / f"{uuid.uuid4().hex}{EXTENSIONS.get(mime, '.bin')}"
            os.replace(tmp, final)
        finally:
            tmp.unlink(missing_ok=True)
        return final, mime

    def decision_failure(exc: Exception, what: str) -> ApiError | None:
        """Erorile motorului la o decizie a omului: necunoscuta -> 404, nu mai este valabila -> 409.

        ApprovalError vine din modulul agent; il recunoastem dupa nume, fara import.
        """
        missing = ApiError(404, f"{what}_not_found", "Nu exista.")
        if isinstance(exc, LookupError):
            return missing
        if type(exc).__name__ == "ApprovalError":
            reason = str(exc).lower()
            if "necunoscut" in reason or "nu exista" in reason:
                return missing
            return ApiError(409, f"{what}_not_available", "Nu mai poate fi folosita; cereti una noua.")
        return None

    def fetcher() -> AttachmentFetcher:
        client = http_client
        if client is None:
            client = clients.get("default")
            if client is None:
                client = clients["default"] = httpx.AsyncClient(
                    follow_redirects=False, trust_env=False, timeout=settings.fetch_timeout_seconds)
        return AttachmentFetcher(
            client=client, allowed_hosts=settings.attachment_hosts, allowed_mimes=settings.allowed_mimes,
            max_bytes=settings.max_attachment_bytes, timeout_seconds=settings.fetch_timeout_seconds,
            resolver=resolver)

    def discard(attachments: list[Attachment]) -> None:
        for item in attachments:
            Path(item.path).unlink(missing_ok=True)

    Loader = Callable[[], Awaitable[list[Attachment]]]

    async def no_attachments() -> list[Attachment]:
        return []

    async def process(contact: Contact, *, message_id: str | None, text: str, button_id: str | None,
                      received_at: datetime, from_staff: bool,
                      load: Loader = no_attachments) -> tuple[list[OutboundAction], bool]:
        """Un mesaj al unei conversatii, pe rand cu celelalte ale aceleiasi conversatii."""
        ref = contact_ref(contact.key, log_salt)
        async with locks.hold((contact.channel, contact.key)):
            if message_id:
                cached = await run_in_threadpool(db.get_response, contact.channel, contact.key, message_id)
                if cached is not None:
                    logger.info("inbound duplicate channel=%s contact=%s", contact.channel, ref)
                    return _ACTIONS.validate_json(cached), True
            attachments = await load()
            message = InboundMessage(contact=contact, message_id=message_id, text=text, button_id=button_id,
                                     attachments=attachments, received_at=received_at,
                                     from_staff=from_staff)
            try:
                result = await run_in_threadpool(engine.handle, message)
                actions = _ACTIONS.validate_python(result)
            except Exception:
                discard(attachments)
                raise
            for action in actions:
                if action.kind == "pending_approval" and action.approval_id:
                    await run_in_threadpool(db.save_approval, action.approval_id, contact.channel, contact.key)
            if message_id:
                await run_in_threadpool(db.save_response, contact.channel, contact.key, message_id,
                                        _ACTIONS.dump_json(actions).decode())
            logger.info("inbound channel=%s contact=%s staff=%s attachments=%d actions=%s",
                        contact.channel, ref, from_staff, len(attachments),
                        ",".join(a.kind for a in actions) or "-")
            return actions, False

    def site_payload(actions: list[OutboundAction], request: Request) -> dict:
        url = media_url_for(request)
        return {
            "actions": [action_for_site(a, url) for a in actions],
            # Widgetul intreaba din nou cat timp asteapta un om (aprobare sau coleg).
            "poll": any(a.kind in ("pending_approval", "handoff") for a in actions),
        }

    # ---------- rute ----------

    @app.get("/health")
    async def health():
        return {"status": "ok", "commit": settings.git_commit}

    @app.post("/v1/inbound")
    async def inbound(body: InboundRequest, request: Request):
        require_secret(request)
        if len(body.attachments) > settings.max_attachments_per_message:
            raise ApiError(422, "too_many_attachments", "Prea multe atasamente intr-un mesaj.")
        contact = Contact(channel=body.channel, key=body.contact.key, phone=body.contact.phone,
                          name=body.contact.name, email=body.contact.email,
                          ad_source=body.contact.ad_source)

        async def load() -> list[Attachment]:
            done: list[Attachment] = []
            if body.from_staff:  # mesajul unui coleg doar trece conversatia pe manual
                return done
            source = fetcher()
            try:
                for item in body.attachments:
                    path, mime = await source.fetch(item.url, item.mime, conversation_dir(contact))
                    done.append(Attachment(path=str(path), mime=mime,
                                           filename=safe_filename(item.filename), public_url=item.url))
            except Exception:
                discard(done)
                raise
            return done

        received = body.received_at
        if received.tzinfo is None:
            received = received.replace(tzinfo=timezone.utc)
        actions, duplicate = await process(
            contact, message_id=body.message_id, text=body.text, button_id=body.button_id,
            received_at=received, from_staff=body.from_staff, load=load)
        url = media_url_for(request)
        return {"message_id": body.message_id, "duplicate": duplicate,
                "actions": [action_for_crm(a, url) for a in actions]}

    def approval_id_or_404(approval_id: str) -> str:
        if not APPROVAL_ID.fullmatch(approval_id):
            raise ApiError(404, "approval_not_found", "Aprobarea nu exista.")
        return approval_id

    @app.post("/v1/approvals/{approval_id}/approve")
    async def approve(approval_id: str, body: ApprovalRequest, request: Request):
        require_secret(request)
        approval_id_or_404(approval_id)
        owner = await run_in_threadpool(db.get_approval, approval_id)
        channel, key = owner or (None, None)
        duplicate = False
        async with locks.hold(owner or ("approval", approval_id)):
            cached = await run_in_threadpool(db.get_response, "approval", approval_id, "approve")
            if cached is not None:
                actions, duplicate = _ACTIONS.validate_json(cached), True
            else:
                try:
                    actions = _ACTIONS.validate_python(await run_in_threadpool(
                        engine.approve, approval_id, body.by, clock(), body.edited_text))
                except Exception as exc:
                    failure = decision_failure(exc, "approval")
                    if failure is None:
                        raise
                    raise failure from None
                payload = _ACTIONS.dump_json(actions).decode()
                if channel == "site" and actions:
                    await run_in_threadpool(db.push_outbox, key, payload)
                await run_in_threadpool(db.save_response, "approval", approval_id, "approve", payload)
        logger.info("approval approved id=%s channel=%s duplicate=%s actions=%d",
                    approval_id, channel or "-", duplicate, len(actions))
        url = media_url_for(request)
        return {
            "approval_id": approval_id, "channel": channel, "key": key, "duplicate": duplicate,
            # site_chat: actiunile sunt deja in coada widgetului, CRM-ul nu are ce livra.
            "delivery": "site_chat" if channel == "site" else "crm",
            "actions": [action_for_crm(a, url) for a in actions],
        }

    @app.post("/v1/approvals/{approval_id}/reject")
    async def reject(approval_id: str, body: ApprovalRequest, request: Request):
        require_secret(request)
        approval_id_or_404(approval_id)
        owner = await run_in_threadpool(db.get_approval, approval_id)
        async with locks.hold(owner or ("approval", approval_id)):
            try:
                await run_in_threadpool(engine.reject, approval_id, body.by, clock())
            except Exception as exc:
                failure = decision_failure(exc, "approval")
                if failure is None:
                    raise
                raise failure from None
        logger.info("approval rejected id=%s", approval_id)
        channel, key = owner or (None, None)
        return {"approval_id": approval_id, "channel": channel, "key": key, "status": "rejected",
                "actions": []}

    @app.get("/v1/media/{token}")
    async def media(token: str):
        try:
            payload = media_signer.verify(token, now_ts())
        except TokenError as exc:
            if exc.reason == "expired":
                raise ApiError(410, "media_expired", "Linkul a expirat.") from None
            raise ApiError(403, "media_invalid", "Link invalid.") from None
        missing = ApiError(404, "not_found", "Fisierul nu exista.")
        rel = payload.get("p")
        if not isinstance(rel, str):
            raise missing
        path = (data_root / rel).resolve()
        if not path.is_relative_to(data_root) or not path.is_file():
            raise missing
        with path.open("rb") as handle:
            mime = sniff_mime(handle.read(16))
        if mime not in MEDIA_MIMES:
            raise missing
        return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, max-age=300"})

    # ---------- chatul de pe site ----------

    @app.post("/v1/chat/session")
    async def chat_session(request: Request, body: ChatSessionRequest | None = None):
        check_rate(limit_sessions, client_ip(request))
        expires = now_ts() + settings.session_ttl_seconds
        payload = {"sid": secrets.token_hex(16)}
        if body and body.ad_source:
            payload["src"] = body.ad_source
        return {"session_token": session_signer.sign(payload, expires), "expires_at": int(expires)}

    @app.post("/v1/chat/message")
    async def chat_message(body: ChatMessageRequest, request: Request):
        ip = client_ip(request)
        contact = session(request)
        check_rate(limit_ip, ip)
        check_rate(limit_session, contact.key)
        actions, _ = await process(contact, message_id=body.message_id, text=body.text,
                                   button_id=body.button_id, received_at=clock(), from_staff=False)
        return site_payload(actions, request)

    @app.post("/v1/chat/upload")
    async def chat_upload(request: Request):
        ip = client_ip(request)
        contact = session(request)
        check_rate(limit_ip, ip)
        check_rate(limit_uploads, contact.key)
        invalid = ApiError(422, "invalid_request", "Cerere invalida.")
        async with request.form(max_files=1, max_fields=3) as form:
            upload, text, message_id = form.get("file"), form.get("text") or "", form.get("message_id")
            if not isinstance(upload, UploadFile) or not isinstance(text, str) or len(text) > 4096:
                raise invalid
            if message_id is not None and not (isinstance(message_id, str) and MESSAGE_ID.fullmatch(message_id)):
                raise invalid

            async def load() -> list[Attachment]:
                path, mime = await save_upload(upload, conversation_dir(contact))
                return [Attachment(path=str(path), mime=mime, filename=safe_filename(upload.filename))]

            actions, _ = await process(contact, message_id=message_id, text=text, button_id=None,
                                       received_at=clock(), from_staff=False, load=load)
        return site_payload(actions, request)

    @app.get("/v1/chat/poll")
    async def chat_poll(request: Request):
        client_ip(request)
        contact = session(request)
        check_rate(limit_polls, contact.key)
        batches = await run_in_threadpool(db.pop_outbox, contact.key)
        actions = [a for batch in batches for a in _ACTIONS.validate_json(batch)]
        return site_payload(actions, request)

    # ---------- mod asistat: extensia Chrome de pe WhatsApp Web ----------
    # Apelurile vin din service worker-ul extensiei, deci fara CORS. Nimic nu se trimite clientului de aici.

    def staff(request: Request) -> str:
        given = request.headers.get("x-ecquote-assist-token")
        name = None
        for candidate, token in assist_tokens:  # fara iesire timpurie
            if secrets_equal(given, token):
                name = candidate
        if name is None:
            raise ApiError(401, "unauthorized", "Token lipsa sau gresit.")
        check_rate(limit_assist, name)
        return name

    def require_assist() -> AssistEngine:
        if assist_engine is None:
            raise ApiError(503, "assist_unavailable", "Modul asistat nu este disponibil.")
        return assist_engine

    @app.get("/v1/assist/ping")
    async def assist_ping(request: Request):
        return {"ok": True, "staff": staff(request)}

    @app.post("/v1/assist/upload")
    async def assist_upload(request: Request):
        name = staff(request)
        invalid = ApiError(422, "invalid_request", "Cerere invalida.")
        async with request.form(max_files=1, max_fields=3) as form:
            upload, chat_key, message_id = form.get("file"), form.get("chat_key"), form.get("message_id")
            if not (isinstance(upload, UploadFile) and isinstance(chat_key, str)
                    and re.fullmatch(ASSIST_KEY_PATTERN, chat_key)
                    and isinstance(message_id, str) and MESSAGE_ID.fullmatch(message_id)):
                raise invalid
            filename = safe_filename(upload.filename)
            # Acelasi (conversatie, mesaj, nume de fisier) da acelasi id: reincarcarea nu dubleaza fisierul.
            upload_id = hmac.new(upload_key, "\0".join((chat_key, message_id, filename or "")).encode(),
                                 hashlib.sha256).hexdigest()[:32]
            async with locks.hold(("whatsapp", chat_key)):
                known = await run_in_threadpool(db.get_upload, upload_id, chat_key)
                if known is None or not Path(known[0]).is_file():
                    path, mime = await save_upload(upload, data_root / "conversations" / "whatsapp"
                                                   / chat_key / "inbound")
                    await run_in_threadpool(db.save_upload, upload_id, chat_key, str(path), mime, filename)
        logger.info("assist upload staff=%s contact=%s", name, contact_ref(chat_key, log_salt))
        return {"upload_id": upload_id}

    @app.post("/v1/assist/suggest")
    async def assist_suggest(body: AssistSuggestRequest, request: Request):
        name = staff(request)
        source = require_assist()
        contact = Contact(channel="whatsapp", key=body.chat.key, phone=body.chat.phone, name=body.chat.name)
        async with locks.hold(("whatsapp", contact.key)):
            messages: list[AssistMessage] = []
            for item in body.messages[-ASSIST_MAX_MESSAGES:]:
                attachments = []
                for ref in item.attachments:
                    found = await run_in_threadpool(db.get_upload, ref.upload_id, contact.key)
                    if found is None:
                        raise ApiError(422, "unknown_upload",
                                       "Fisierul nu a fost incarcat pentru aceasta conversatie.")
                    attachments.append(Attachment(path=found[0], mime=found[1], filename=found[2]))
                sent = item.sent_at
                if sent is not None and sent.tzinfo is None:
                    sent = sent.replace(tzinfo=timezone.utc)
                messages.append(AssistMessage(id=item.id, direction=item.direction,
                                              text=item.text[:ASSIST_MAX_TEXT], sent_at=sent,
                                              attachments=attachments))
            suggestion = AssistSuggestion.model_validate(
                await run_in_threadpool(source.suggest, contact, messages, clock()))
            await run_in_threadpool(db.save_approval, suggestion.suggestion_id, "assist", contact.key)
        logger.info("assist suggest staff=%s contact=%s messages=%d kind=%s", name,
                    contact_ref(contact.key, log_salt), len(messages), suggestion.kind)
        return suggestion_payload(suggestion, media_url_for(request))

    @app.post("/v1/assist/suggestions/{suggestion_id}/payment-link")
    async def assist_payment_link(suggestion_id: str, request: Request,
                                  body: AssistPaymentLinkRequest | None = None):
        name = staff(request)
        source = require_assist()
        if not APPROVAL_ID.fullmatch(suggestion_id):
            raise ApiError(404, "suggestion_not_found", "Nu exista.")
        owner = await run_in_threadpool(db.get_approval, suggestion_id)
        key = owner[1] if owner and owner[0] == "assist" else None
        async with locks.hold(("whatsapp", key) if key else ("suggestion", suggestion_id)):
            try:
                suggestion = AssistSuggestion.model_validate(await run_in_threadpool(
                    source.create_payment_link, suggestion_id, name, clock(),
                    body.edited_text if body else None))
            except Exception as exc:
                failure = decision_failure(exc, "suggestion")
                if failure is None:
                    raise
                raise failure from None
        logger.info("assist payment link staff=%s contact=%s", name,
                    contact_ref(key, log_salt) if key else "-")
        return suggestion_payload(suggestion, media_url_for(request))

    if settings.demo:
        # Pagina de proba si fisierele widgetului, doar cu EC_QUOTE_DEMO=1.
        app.mount("/demo", StaticFiles(directory=STATIC_DIR, html=True), name="demo")

    return app
