"""Formatul pe fir al API-ului: cereri, raspunsuri si serializarea actiunilor pe canal."""
from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ec_quote.api import texts
from ec_quote.contracts import AssistSuggestion, Channel, OutboundAction

WA_KEY_PATTERN = r"^[0-9]{6,20}$"
SITE_KEY_PATTERN = r"^[0-9a-f]{32}$"

Text = Annotated[str, StringConstraints(max_length=4096)]
Short = Annotated[str, StringConstraints(max_length=256)]
MediaUrl = Callable[[str], str]
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
        pattern = WA_KEY_PATTERN if self.channel == "whatsapp" else SITE_KEY_PATTERN
        if not re.fullmatch(pattern, self.contact.key):
            raise ValueError("contact.key nu are forma canalului")
        return self


class ApprovalRequest(_Strict):
    by: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    edited_text: Text | None = None  # omul a corectat textul ofertei inainte de aprobare


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


# ---------- mod asistat (extensia Chrome) ----------

ASSIST_KEY_PATTERN = r"^[A-Za-z0-9](?:[A-Za-z0-9_.@-]{0,62}[A-Za-z0-9])?$"
ASSIST_MAX_MESSAGES = 40      # motorul primeste ultimele 40
ASSIST_MAX_TEXT = 4096        # textul mai lung se scurteaza, nu se respinge
UploadId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


class AssistChat(_Strict):
    key: Annotated[str, StringConstraints(pattern=ASSIST_KEY_PATTERN)]
    name: Short | None = None
    phone: Annotated[str, StringConstraints(max_length=32)] | None = None


class AssistAttachmentRef(_Strict):
    upload_id: UploadId


class AssistPendingAttachmentIn(_Strict):
    kind: Literal["image", "document"]
    filename: Short | None = None


class AssistMessageIn(_Strict):
    id: MessageId
    direction: Literal["in", "out"]
    text: Annotated[str, StringConstraints(max_length=70000)] = ""
    quoted_text: Annotated[str, StringConstraints(max_length=1000)] | None = None
    sent_at: datetime | None = None
    attachments: Annotated[list[AssistAttachmentRef], Field(max_length=5)] = Field(default_factory=list)
    unuploaded_attachments: Annotated[list[AssistPendingAttachmentIn], Field(max_length=5)] = Field(
        default_factory=list
    )


class AssistSuggestRequest(_Strict):
    chat: AssistChat
    messages: Annotated[list[AssistMessageIn], Field(max_length=500)]


class AssistPaymentLinkRequest(_Strict):
    edited_text: Text | None = None


def suggestion_payload(suggestion: AssistSuggestion, media_url: MediaUrl) -> dict:
    """Sugestia pentru extensie: banii ca text, imaginea ca link semnat, fara cai locale."""
    data = suggestion.model_dump(mode="json", exclude={"image_path"})
    data["image_url"] = media_url(suggestion.image_path) if suggestion.image_path else None
    return {"suggestion": data}



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
