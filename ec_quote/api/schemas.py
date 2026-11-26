"""Formatul pe fir al API-ului: cereri, raspunsuri si serializarea actiunilor pe canal."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ec_quote.api import texts
from ec_quote.contracts import Channel, OutboundAction

WA_KEY_PATTERN = r"^[0-9]{6,20}$"
SITE_KEY_PATTERN = r"^[0-9a-f]{32}$"

Text = Annotated[str, StringConstraints(max_length=4096)]
Short = Annotated[str, StringConstraints(max_length=256)]
MessageId = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r"^[\x21-\x7e]+$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InboundContact(_Strict):
    key: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    phone: Annotated[str, StringConstraints(max_length=32)] | None = None
    name: Short | None = None
    email: Short | None = None
    ad_source: Short | None = None


class InboundAttachment(_Strict):
    url: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    mime: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    filename: Short | None = None


class InboundRequest(_Strict):
    channel: Channel
    contact: InboundContact
    message_id: MessageId
    text: Text = ""
    button_id: Short | None = None
    attachments: list[InboundAttachment] = Field(default_factory=list)
    received_at: datetime
    from_staff: bool = False

    @model_validator(mode="after")
    def _key_matches_channel(self):
        import re

        pattern = WA_KEY_PATTERN if self.channel == "whatsapp" else SITE_KEY_PATTERN
        if not re.fullmatch(pattern, self.contact.key):
            raise ValueError("contact.key nu are forma canalului")
        return self


class ApprovalRequest(_Strict):
    by: Annotated[str, StringConstraints(min_length=1, max_length=120)]


class ChatSessionRequest(_Strict):
    ad_source: Short | None = None


class ChatMessageRequest(_Strict):
    text: Text = ""
    button_id: Short | None = None
    message_id: MessageId | None = None

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.text.strip() and not self.button_id:
            raise ValueError("text sau button_id este obligatoriu")
        return self


MediaUrl = Callable[[str], str]


def action_for_crm(action: OutboundAction, media_url: MediaUrl) -> dict:
    """CRM-ul primeste tot, inclusiv oferta in asteptare (o vede omul care aproba)."""
    return {
        "kind": action.kind,
        "text": action.text,
        "buttons": [{"id": b.id, "title": b.title} for b in action.buttons],
        "image_url": media_url(action.image_path) if action.image_path else None,
        "handoff_reason": action.handoff_reason.value if action.handoff_reason else None,
        "approval_id": action.approval_id,
    }


def action_for_site(action: OutboundAction, media_url: MediaUrl) -> dict:
    """Widgetul primeste doar ce are de afisat. O actiune in asteptare devine un anunt neutru."""
    if action.kind == "pending_approval":
        return {"kind": "notice", "text": texts.PENDING_OFFER, "buttons": [], "image_url": None}
    if action.kind == "handoff":
        return {"kind": "handoff", "text": action.text or texts.HANDOFF, "buttons": [], "image_url": None}
    return {
        "kind": action.kind,
        "text": action.text,
        "buttons": [{"id": b.id, "title": b.title} for b in action.buttons],
        "image_url": media_url(action.image_path) if action.image_path else None,
    }
