import json
from pathlib import Path

import pytest
from PIL import Image

from ec_quote.mockup import MockupService

GRAY = (128, 128, 128)
MAGENTA = (230, 0, 160)


def write_template(root: Path, template_id: str = "plat", *, size=(1000, 800), **overrides) -> Path:
    """Sablon minim de test: fotografie gri uniforma si un manifest valid."""
    folder = root / template_id
    folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, GRAY).save(folder / "photo.png")
    manifest = {
        "id": template_id, "title": "Sablon de test", "photo": "photo.png",
        "keywords": ["test"], "quad": [[300, 200], [700, 200], [700, 600], [300, 600]],
        "label_shape": "rectangle", "padding": 0,
    }
    manifest.update(overrides)
    (folder / "template.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


@pytest.fixture
def solid_design(tmp_path):
    path = tmp_path / "design.png"
    Image.new("RGB", (400, 400), MAGENTA).save(path)
    return str(path)


@pytest.fixture(scope="session")
def service():
    return MockupService()
