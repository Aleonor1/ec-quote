"""Implementarea MockupPort."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from threading import Lock

from ..contracts import MockupResult, OfferLine
from .compose import digest, load_design, render_mockup, save_jpeg, template_fingerprint
from .offer import offer_digest, render_offer
from .templates import Template, load_templates, select_template

TEMPLATES_ENV = "EC_QUOTE_TEMPLATES_DIR"


def default_templates_dir() -> Path:
    override = os.environ.get(TEMPLATES_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "templates" / "mockups"


class MockupService:
    """MockupPort peste un director de sabloane. Sabloanele se incarca o data, la prima folosire."""

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        self._dir = Path(templates_dir) if templates_dir is not None else None
        self._templates: list[Template] | None = None
        self._lock = Lock()

    @property
    def templates(self) -> list[Template]:
        with self._lock:
            if self._templates is None:
                self._templates = load_templates(self._dir or default_templates_dir())
            return self._templates

    def reload(self) -> None:
        with self._lock:
            self._templates = None

    def choose_template(self, context_hint: str) -> Template:
        return select_template(self.templates, context_hint)

    def is_placeholder(self, template_id: str) -> bool:
        return any(t.id == template_id and t.manifest.placeholder for t in self.templates)

    def make_mockup(self, design_path: str, context_hint: str, out_dir: str) -> MockupResult:
        design = load_design(design_path)
        template = self.choose_template(context_hint)
        name = "mockup-%s-%s.jpg" % (
            template.id, digest(Path(design_path).read_bytes(), template_fingerprint(template)))
        out_path = Path(out_dir) / name
        save_jpeg(render_mockup(template, design), out_path)
        return MockupResult(template_id=template.id, image_path=str(out_path))

    def make_offer_image(
        self, mockup_path: str | None, lines: list[OfferLine], production_term: str,
        valid_until: datetime, out_dir: str,
    ) -> str:
        image = render_offer(mockup_path, lines, production_term, valid_until)
        name = "oferta-%s.jpg" % offer_digest(mockup_path, lines, production_term, valid_until)
        out_path = Path(out_dir) / name
        save_jpeg(image, out_path)
        return str(out_path)


_default = MockupService()


def make_mockup(design_path: str, context_hint: str, out_dir: str) -> MockupResult:
    return _default.make_mockup(design_path, context_hint, out_dir)


def make_offer_image(
    mockup_path: str | None, lines: list[OfferLine], production_term: str,
    valid_until: datetime, out_dir: str,
) -> str:
    return _default.make_offer_image(mockup_path, lines, production_term, valid_until, out_dir)
