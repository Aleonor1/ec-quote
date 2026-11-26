"""Sabloanele foto: manifest strict (pydantic), incarcare si alegere dupa cuvinte cheie."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .errors import NoTemplatesError, TemplateError

MANIFEST_NAME = "template.json"
_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FILE_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png)$")
_STEM_MIN = 4  # de la 4 litere in sus, cuvantul cheie prinde si formele flexionate

LabelShape = Literal["rectangle", "rounded", "circle", "oval"]


def normalize_text(text: str) -> str:
    """Litere mici, fara diacritice, doar litere si cifre separate de un spatiu."""
    text = text.replace("ß", "ss")
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    return " ".join(re.findall(r"[a-z0-9]+", plain))


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Cylinder(_Strict):
    """Curbura pentru borcane, sticle, pahare."""

    wrap_degrees: float = Field(gt=10, le=170)   # cat din circumferinta acopera zona
    arc_px: float = Field(default=0, ge=-400, le=400)  # cu cat coboara mijlocul fata de colturi
    edge_shade: float = Field(default=0, ge=0, le=0.8)  # intunecare spre margini, fara shade.png


class Blend(_Strict):
    """Cum preia eticheta lumina din fotografie."""

    shade: str | None = None          # harta gri: 128 neutru, sub 128 umbra, peste 128 luciu
    photo_luminance: bool = False     # umbrele se iau direct din fotografie (suprafata uniforma)
    strength: float = Field(default=0.8, ge=0, le=1)
    opacity: float = Field(default=1.0, gt=0, le=1)
    mask: str | None = None           # alb = eticheta vizibila, negru = acoperita de obiecte

    @field_validator("shade", "mask")
    @classmethod
    def _file_name(cls, value: str | None) -> str | None:
        if value is not None and not _FILE_RE.match(value):
            raise ValueError("nume de fisier simplu, .png sau .jpg, fara cale")
        return value

    @model_validator(mode="after")
    def _one_source(self) -> "Blend":
        if self.shade and self.photo_luminance:
            raise ValueError("alege fie shade, fie photo_luminance")
        return self


class TemplateManifest(_Strict):
    id: str
    title: str = Field(min_length=1, max_length=80)
    placeholder: bool = False
    default: bool = False
    photo: str = "photo.jpg"
    keywords: list[str] = Field(min_length=1)
    quad: list[tuple[float, float]]   # TL, TR, BR, BL in pixelii fotografiei
    label_shape: LabelShape = "rounded"
    padding: float = Field(default=0.04, ge=0, le=0.4)  # margine libera in zona, ca fractie
    cylinder: Cylinder | None = None
    blend: Blend = Field(default_factory=Blend)

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError("id: litere mici, cifre si cratima")
        return value

    @field_validator("photo")
    @classmethod
    def _photo(cls, value: str) -> str:
        if not _FILE_RE.match(value):
            raise ValueError("nume de fisier simplu, .jpg sau .png, fara cale")
        return value

    @field_validator("keywords")
    @classmethod
    def _keywords(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for raw in value:
            if not normalize_text(raw):
                raise ValueError("cuvant cheie gol: %r" % raw)
            if normalize_text(raw) in (normalize_text(s) for s in seen):
                raise ValueError("cuvant cheie repetat: %r" % raw)
            seen.append(raw)
        return value

    @field_validator("quad")
    @classmethod
    def _quad(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(value) != 4:
            raise ValueError("quad are exact 4 puncte: stanga sus, dreapta sus, dreapta jos, stanga jos")
        area2 = 0.0
        for i in range(4):
            a, b, c = value[i], value[(i + 1) % 4], value[(i + 2) % 4]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if cross <= 0:
                raise ValueError("quad trebuie sa fie convex, in sensul acelor de ceas, pornind din stanga sus")
            area2 += a[0] * b[1] - b[0] * a[1]
        if area2 / 2 < 400:
            raise ValueError("zona este prea mica")
        tl, tr, br, bl = value
        if not (tl[0] < tr[0] and bl[0] < br[0] and tl[1] < bl[1] and tr[1] < br[1]):
            raise ValueError("ordinea punctelor: stanga sus, dreapta sus, dreapta jos, stanga jos")
        return value


@dataclass(frozen=True)
class Template:
    manifest: TemplateManifest
    directory: Path
    photo_size: tuple[int, int]

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def photo_path(self) -> Path:
        return self.directory / self.manifest.photo

    def file(self, name: str) -> Path:
        return self.directory / name


def _image_size(path: Path, what: str) -> tuple[int, int]:
    if not path.is_file():
        raise TemplateError("%s lipseste: %s" % (what, path))
    try:
        with Image.open(path) as im:
            return im.size
    except Exception as exc:  # Pillow ridica tipuri diferite pentru fisiere stricate
        raise TemplateError("%s nu se poate citi: %s" % (what, path)) from exc


def load_template(directory: str | Path) -> Template:
    """Incarca si valideaza un sablon. Orice problema devine TemplateError."""
    directory = Path(directory)
    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.is_file():
        raise TemplateError("lipseste %s in %s" % (MANIFEST_NAME, directory))
    try:
        manifest = TemplateManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    except (ValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TemplateError("manifest invalid %s: %s" % (manifest_path, exc)) from exc
    if manifest.id != directory.name:
        raise TemplateError("id-ul %r nu este numele folderului %r" % (manifest.id, directory.name))
    size = _image_size(directory / manifest.photo, "fotografia")
    if max(size) < 800:
        raise TemplateError("fotografia este prea mica (%dx%d), minim 800 px pe latura lunga" % size)
    for x, y in manifest.quad:
        if not (0 <= x <= size[0] and 0 <= y <= size[1]):
            raise TemplateError("punctul (%s, %s) este in afara fotografiei %dx%d" % (x, y, *size))
    for name, what in ((manifest.blend.shade, "shade"), (manifest.blend.mask, "mask")):
        if name and _image_size(directory / name, what) != size:
            raise TemplateError("%s trebuie sa aiba exact marimea fotografiei (%dx%d)" % (what, *size))
    return Template(manifest=manifest, directory=directory, photo_size=size)


def load_templates(root: str | Path) -> list[Template]:
    """Toate sabloanele din `root`, sortate dupa id. Exact unul este cel implicit."""
    root = Path(root)
    if not root.is_dir():
        raise NoTemplatesError("directorul de sabloane nu exista: %s" % root)
    templates = [
        load_template(child) for child in sorted(root.iterdir())
        if child.is_dir() and (child / MANIFEST_NAME).is_file()
    ]
    if not templates:
        raise NoTemplatesError("niciun sablon in %s" % root)
    defaults = [t.id for t in templates if t.manifest.default]
    if len(defaults) > 1:
        raise TemplateError("mai multe sabloane implicite: %s" % ", ".join(defaults))
    return templates


def default_template(templates: list[Template]) -> Template:
    for template in templates:
        if template.manifest.default:
            return template
    return templates[0]


def _match(keyword: str, tokens: list[str]) -> tuple[int, int] | None:
    """Pozitia primei potriviri si lungimea ei, sau None."""
    words = keyword.split()
    for start in range(len(tokens) - len(words) + 1):
        for offset, word in enumerate(words):
            token = tokens[start + offset]
            if token != word and not (len(word) >= _STEM_MIN and token.startswith(word)):
                break
        else:
            return start, len(keyword)
    return None


def select_template(templates: list[Template], context_hint: str) -> Template:
    """Sablonul al carui cuvant cheie apare primul in context; la egalitate, potrivirea mai lunga.

    In romana substantivul principal vine primul ("borcan de sticla", "cutie de cafea").
    """
    if not templates:
        raise NoTemplatesError("niciun sablon incarcat")
    tokens = normalize_text(context_hint or "").split()
    best: tuple[tuple[int, int, str], Template] | None = None
    for template in templates:
        for keyword in template.manifest.keywords:
            found = _match(normalize_text(keyword), tokens)
            if found is None:
                continue
            rank = (found[0], -found[1], template.id)
            if best is None or rank < best[0]:
                best = (rank, template)
    return best[1] if best else default_template(templates)
