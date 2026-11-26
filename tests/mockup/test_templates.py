import json

import pytest
from PIL import Image
from pydantic import ValidationError

from ec_quote.mockup import (
    MockupService, NoTemplatesError, TemplateError, TemplateManifest, load_template, load_templates,
    select_template,
)
from ec_quote.mockup.service import TEMPLATES_ENV, default_templates_dir
from ec_quote.mockup.templates import default_template, normalize_text

from .conftest import write_template

VALID = {
    "id": "plat", "title": "Test", "keywords": ["test"],
    "quad": [[300, 200], [700, 200], [700, 600], [300, 600]],
}


# ---------- alegerea sablonului ----------

@pytest.mark.parametrize("hint, expected", [
    ("etichete pentru borcane de miere", "borcan"),
    ("BORCAN", "borcan"),
    ("dulceață de casă", "borcan"),
    ("dulceata", "borcan"),
    ("borcan de sticlă 720 ml", "borcan"),
    ("pahar de cafea", "pahar-cafea"),
    ("stickere pentru pahare to go", "pahar-cafea"),
    ("cafenea", "pahar-cafea"),
    ("cutie de cafea", "cutie"),
    ("cutii pizza", "cutie"),
    ("sticlă de vin", "sticla"),
    ("STICLĂ", "sticla"),
    ("sticle bere artizanală", "sticla"),
    ("țuică", "sticla"),
    ("tuica de prune", "sticla"),
    ("pungă kraft", "punga-kraft"),
    ("punga kraft pentru cafea boabe", "punga-kraft"),
    ("pungi", "punga-kraft"),
    ("logo firma", "cutie"),
    ("", "cutie"),
    ("   ", "cutie"),
    ("vinil auto", "cutie"),
])
def test_template_selection(service, hint, expected):
    assert service.choose_template(hint).id == expected


def test_selection_ignores_diacritics_and_case():
    assert normalize_text("  PUNGĂ   Kraft, Țuică și şnur ") == "punga kraft tuica si snur"


def test_short_keywords_match_whole_words_only(service):
    # "vin" nu trebuie sa prinda "vinil" sau "vineri"
    assert service.choose_template("vinil pentru vineri").id == "cutie"
    assert service.choose_template("vin rosu").id == "sticla"


def test_first_mention_wins_then_longer_keyword(tmp_path):
    write_template(tmp_path, "a", keywords=["pungă"])
    write_template(tmp_path, "b", keywords=["pungă kraft"], default=True)
    write_template(tmp_path, "c", keywords=["cafea"])
    templates = load_templates(tmp_path)
    assert select_template(templates, "punga kraft cafea").id == "b"
    assert select_template(templates, "cafea in punga").id == "c"
    assert select_template(templates, "nimic").id == "b"
    assert select_template(templates, None).id == "b"
    with pytest.raises(NoTemplatesError):
        select_template([], "orice")


def test_default_is_first_by_id_when_none_is_marked(tmp_path):
    write_template(tmp_path, "zeta")
    write_template(tmp_path, "alfa")
    assert default_template(load_templates(tmp_path)).id == "alfa"


def test_shipped_templates_are_valid_placeholders(service):
    ids = [t.id for t in service.templates]
    assert ids == ["borcan", "cutie", "pahar-cafea", "punga-kraft", "sticla"]
    assert all(t.manifest.placeholder for t in service.templates)
    assert all(service.is_placeholder(i) for i in ids)
    assert not service.is_placeholder("inexistent")
    assert [t.id for t in service.templates if t.manifest.default] == ["cutie"]
    assert all(max(t.photo_size) == 1600 for t in service.templates)


def test_templates_dir_from_environment(monkeypatch, tmp_path):
    write_template(tmp_path, "unic")
    monkeypatch.setenv(TEMPLATES_ENV, str(tmp_path))
    assert default_templates_dir() == tmp_path
    svc = MockupService()
    assert [t.id for t in svc.templates] == ["unic"]
    write_template(tmp_path, "altul")
    assert len(svc.templates) == 1
    svc.reload()
    assert len(svc.templates) == 2


# ---------- validarea manifestului ----------

def test_valid_manifest_defaults():
    manifest = TemplateManifest.model_validate(VALID)
    assert manifest.photo == "photo.jpg"
    assert manifest.label_shape == "rounded"
    assert manifest.cylinder is None
    assert manifest.blend.shade is None and not manifest.placeholder


@pytest.mark.parametrize("patch", [
    {"id": "Cu Spatii"},
    {"id": "../sus"},
    {"title": ""},
    {"keywords": []},
    {"keywords": ["  "]},
    {"keywords": ["miere", "Miere"]},
    {"quad": [[0, 0], [10, 0], [10, 10]]},
    {"quad": [[300, 200], [700, 200], [300, 600], [700, 600]]},      # incrucisat
    {"quad": [[300, 200], [300, 600], [700, 600], [700, 200]]},      # sens invers
    {"quad": [[700, 200], [700, 600], [300, 600], [300, 200]]},      # nu porneste din stanga sus
    {"quad": [[300, 200], [700, 200], [450, 300], [300, 600]]},      # concav
    {"quad": [[0, 0], [5, 0], [5, 5], [0, 5]]},                      # prea mic
    {"quad": "nu"},
    {"label_shape": "stea"},
    {"padding": 0.9},
    {"photo": "../photo.jpg"},
    {"photo": "photo.gif"},
    {"cylinder": {"wrap_degrees": 0}},
    {"cylinder": {"wrap_degrees": 200}},
    {"cylinder": {"wrap_degrees": 90, "raza": 3}},
    {"cylinder": {}},
    {"blend": {"strength": 2}},
    {"blend": {"opacity": 0}},
    {"blend": {"shade": "a/b.png"}},
    {"blend": {"shade": "shade.png", "photo_luminance": True}},
    {"blend": {"mod": "multiply"}},
    {"camp_necunoscut": 1},
    {"placeholder": "poate"},
])
def test_invalid_manifests_are_rejected(patch):
    with pytest.raises(ValidationError):
        TemplateManifest.model_validate({**VALID, **patch})


@pytest.mark.parametrize("missing", ["id", "title", "keywords", "quad"])
def test_required_fields(missing):
    data = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(ValidationError):
        TemplateManifest.model_validate(data)


def test_load_template_ok(tmp_path):
    template = load_template(write_template(tmp_path))
    assert template.id == "plat"
    assert template.photo_size == (1000, 800)
    assert template.photo_path.name == "photo.png"


def test_load_template_errors(tmp_path):
    with pytest.raises(TemplateError, match="lipseste"):
        load_template(tmp_path / "nimic")

    folder = write_template(tmp_path, "a")
    (folder / "template.json").write_text("{nu e json", encoding="utf-8")
    with pytest.raises(TemplateError, match="manifest invalid"):
        load_template(folder)

    folder = write_template(tmp_path, "b", label_shape="stea")
    with pytest.raises(TemplateError, match="manifest invalid"):
        load_template(folder)

    folder = write_template(tmp_path, "c", id="altceva")
    with pytest.raises(TemplateError, match="numele folderului"):
        load_template(folder)

    folder = write_template(tmp_path, "d")
    (folder / "photo.png").unlink()
    with pytest.raises(TemplateError, match="lipseste"):
        load_template(folder)

    folder = write_template(tmp_path, "e")
    (folder / "photo.png").write_bytes(b"nu e imagine")
    with pytest.raises(TemplateError, match="nu se poate citi"):
        load_template(folder)

    folder = write_template(tmp_path, "f", size=(400, 300), quad=[[10, 10], [300, 10], [300, 200], [10, 200]])
    with pytest.raises(TemplateError, match="prea mica"):
        load_template(folder)

    folder = write_template(tmp_path, "g", quad=[[300, 200], [1200, 200], [1200, 600], [300, 600]])
    with pytest.raises(TemplateError, match="in afara fotografiei"):
        load_template(folder)

    folder = write_template(tmp_path, "h", blend={"shade": "shade.png"})
    with pytest.raises(TemplateError, match="lipseste"):
        load_template(folder)
    Image.new("L", (10, 10)).save(folder / "shade.png")
    with pytest.raises(TemplateError, match="exact marimea"):
        load_template(folder)

    folder = write_template(tmp_path, "i", blend={"mask": "mask.png"})
    Image.new("L", (1000, 800), 255).save(folder / "mask.png")
    assert load_template(folder).manifest.blend.mask == "mask.png"


def test_load_templates_errors(tmp_path):
    with pytest.raises(NoTemplatesError):
        load_templates(tmp_path / "lipsa")
    with pytest.raises(NoTemplatesError):
        load_templates(tmp_path)
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "fara-manifest").mkdir()
    write_template(tmp_path, "a", default=True)
    assert [t.id for t in load_templates(tmp_path)] == ["a"]
    write_template(tmp_path, "b", default=True)
    with pytest.raises(TemplateError, match="mai multe sabloane implicite"):
        load_templates(tmp_path)


def test_manifests_on_disk_are_strict_json(service):
    for template in service.templates:
        raw = json.loads((template.directory / "template.json").read_text(encoding="utf-8"))
        assert raw["id"] == template.directory.name
        assert raw["placeholder"] is True
