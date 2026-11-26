import json

from PIL import Image

from ec_quote.mockup import load_templates
from ec_quote.mockup.make_placeholders import WATERMARK, generate, main
from ec_quote.mockup.service import default_templates_dir


def test_generator_reproduces_the_committed_manifests(tmp_path):
    folders = generate(tmp_path)
    assert sorted(f.name for f in folders) == ["borcan", "cutie", "pahar-cafea", "punga-kraft", "sticla"]
    shipped = default_templates_dir()
    for folder in folders:
        fresh = json.loads((folder / "template.json").read_text(encoding="utf-8"))
        committed = json.loads((shipped / folder.name / "template.json").read_text(encoding="utf-8"))
        assert fresh == committed
        assert fresh["placeholder"] is True and "provizoriu" in fresh["title"]
        with Image.open(folder / "photo.jpg") as photo:
            assert photo.size == (1600, 1200)
        if fresh["blend"]["shade"]:
            with Image.open(folder / "shade.png") as shade:
                assert shade.size == (1600, 1200) and shade.mode == "L"
                assert shade.getpixel((10, 10)) == 128
    assert len(load_templates(tmp_path)) == 5
    assert WATERMARK == "SABLON PROVIZORIU"


def test_generator_is_deterministic_and_watermark_is_optional(tmp_path, capsys):
    generate(tmp_path / "a")
    assert main([str(tmp_path / "b")]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 5
    for name in ("borcan", "punga-kraft"):
        assert (tmp_path / "a" / name / "photo.jpg").read_bytes() == (tmp_path / "b" / name / "photo.jpg").read_bytes()
    main([str(tmp_path / "c"), "--fara-text"])
    corner = (30, 1150, 330, 1180)
    marked = Image.open(tmp_path / "a" / "cutie" / "photo.jpg").convert("L").crop(corner)
    clean = Image.open(tmp_path / "c" / "cutie" / "photo.jpg").convert("L").crop(corner)
    assert marked.getextrema()[0] < clean.getextrema()[0] - 25
