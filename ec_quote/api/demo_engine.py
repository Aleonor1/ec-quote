"""Motor demonstrativ pentru pagina de proba a widgetului. Nu calculeaza preturi si nu este folosit in productie.

Raspunde dupa cuvinte cheie, ca sa se vada fiecare fel de actiune: text, butoane,
imagine, predare catre un coleg si oferta in asteptarea aprobarii.
"""
from __future__ import annotations

import struct
import zlib
from datetime import datetime
from pathlib import Path

from ec_quote.contracts import Button, HandoffReason, InboundMessage, OutboundAction


def write_png(path: Path, width: int = 480, height: int = 300) -> None:
    """Un PNG simplu (dungi), scris doar cu biblioteca standard."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            band = ((x + y) // 40) % 2
            rows += bytes((228, 87, 46)) if band else bytes((250, 240, 225))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b""))


class DemoEngine:
    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._pending: dict[str, str] = {}

    def _image(self, key: str) -> str:
        path = self._data_dir / "conversations" / "site" / key / "out" / "demo-oferta.png"
        if not path.exists():
            write_png(path)
        return str(path)

    def handle(self, message: InboundMessage) -> list[OutboundAction]:
        key = message.contact.key
        text = message.text.lower()
        if message.attachments:
            return [OutboundAction(kind="text", text="Am primit fișierul. Arată bine pentru tipar."),
                    OutboundAction(kind="image", text="Simulare pe produs (exemplu demonstrativ).",
                                   image_path=self._image(key))]
        if message.button_id == "demo_file" or "fisier" in text or "fișier" in text:
            return [OutboundAction(kind="text", text="Atașați fișierul cu butonul din stânga câmpului de mesaj.")]
        if message.button_id == "demo_human" or "coleg" in text:
            return [OutboundAction(kind="handoff", handoff_reason=HandoffReason.CUSTOMER_ASKED)]
        if message.button_id == "demo_offer" or "ofert" in text:
            approval_id = f"demo-{key[:8]}"
            self._pending[approval_id] = key
            return [OutboundAction(kind="pending_approval", approval_id=approval_id,
                                   text="Oferta demonstrativa, nevazuta de client pana la aprobare.")]
        return [
            OutboundAction(kind="text", text="Acesta este un mediu de probă, fără prețuri reale. "
                                             "Detalii: https://etichetecreative.ro"),
            OutboundAction(kind="buttons", text="Ce doriți să încercați?", buttons=[
                Button(id="demo_offer", title="Cer o ofertă"),
                Button(id="demo_file", title="Trimit un fișier"),
                Button(id="demo_human", title="Vorbesc cu un coleg"),
            ]),
        ]

    def approve(self, approval_id: str, approved_by: str, now: datetime,
                edited_text: str | None = None) -> list[OutboundAction]:
        key = self._pending.pop(approval_id)  # KeyError -> 404 in API
        return [OutboundAction(kind="image", text="Oferta dumneavoastră (exemplu demonstrativ).",
                               image_path=self._image(key))]

    def reject(self, approval_id: str, rejected_by: str, now: datetime) -> None:
        self._pending.pop(approval_id)


def build_engine(settings, clock=None) -> DemoEngine:
    return DemoEngine(settings.data_dir)
