"""Genereaza `docs/intrebari-pentru-owner.md` din intrarile `needs_owner` si din contradictii.

    python3 -m ec_quote.knowledge.export_questions            # scrie fisierul
    python3 -m ec_quote.knowledge.export_questions --check    # verifica doar ca fisierul este la zi
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ec_quote.knowledge.loader import KnowledgeContent, default_knowledge_dir, load_content

_TITLES = {
    "rezistenta": "Rezistența materialelor",
    "materiale": "Materiale, finisaje și adeziv",
    "comanda": "Comandă și cantități",
    "termene": "Termene și urgențe",
    "livrare": "Livrare",
    "plata": "Plată și facturare",
    "fisiere": "Fișiere și grafică",
    "retur": "Retur și reclamații",
    "contact": "Contact și program",
    "mostre": "Mostre",
}


def _title(topic: str) -> str:
    return _TITLES.get(topic, topic.capitalize())


def render(content: KnowledgeContent) -> str:
    """Textul complet al documentului. Determinist: aceeasi baza da acelasi text."""
    open_entries = [entry for entry in content.entries if entry.status == "needs_owner"]
    verified = len(content.entries) - len(open_entries)
    checked = max(entry.last_checked for entry in content.entries)
    lines = [
        "# Întrebări pentru owner",
        "",
        "Fișier generat cu `python3 -m ec_quote.knowledge.export_questions`. Nu se editează de mână:",
        "răspunsurile se trec în `knowledge/<subiect>.json`, la intrarea cu id-ul din paranteză.",
        "",
        f"Stare la {checked}: {verified} răspunsuri verificate, {len(open_entries)} întrebări deschise, "
        f"{len(content.contradictions)} contradicții între surse.",
        "",
        "Până primesc răspuns, asistentul nu spune nimic clienților despre aceste subiecte:",
        "sugestia apare ca „de văzut de om”.",
        "",
        "## Întrebări deschise",
    ]
    topics: list[str] = []
    for entry in open_entries:
        if entry.topic not in topics:
            topics.append(entry.topic)
    number = 0
    for topic in topics:
        lines += ["", f"### {_title(topic)}", ""]
        for entry in open_entries:
            if entry.topic != topic:
                continue
            number += 1
            lines.append(f"{number}. {entry.owner_question} (`{entry.id}`)")
            lines.append(f"   - Clientul întreabă: „{entry.question}”")
            if entry.source:
                lines.append(f"   - Ce am găsit: {entry.source}")
    lines += ["", "## Contradicții între surse", ""]
    if not content.contradictions:
        lines.append("Nicio contradicție găsită.")
    for index, item in enumerate(content.contradictions, start=1):
        lines.append(f"{index}. {item.question} (`{item.id}`, {_title(item.topic)})")
        lines.append(f"   - Ce am găsit: {item.summary}")
        lines.append(f"   - Surse: {'; '.join(item.sources)}")
    return "\n".join(lines) + "\n"


def default_output() -> Path:
    return default_knowledge_dir().parent / "docs" / "intrebari-pentru-owner.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta intrebarile deschise pentru owner.")
    parser.add_argument("--knowledge-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="nu scrie; iese cu 1 daca fisierul nu este la zi")
    args = parser.parse_args(argv)
    text = render(load_content(args.knowledge_dir))
    out = args.out or default_output()
    if args.check:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if current != text:
            print(f"{out} nu este la zi; ruleaza python3 -m ec_quote.knowledge.export_questions", file=sys.stderr)
            return 1
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(out.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, out)
    print(f"{out}: {text.count(chr(10))} randuri")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
