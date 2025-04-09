"""
Script to convert anchor key-value pairs into Anki flashcards.

This script takes a JSON file containing anchor pairs and creates Anki flashcards
using different cloze deletion templates. It supports various formatting options
and ensures proper card creation through the AnkiConnect API.
"""
import fire
import json
from pathlib import Path
from py_ankiconnect import PyAnkiconnect

call_anki = PyAnkiconnect()

TEMPLATES = {
    1: """{{c1::K}}<br/><br/>{{c2::V}}""",
    2: """{{c1::K}}<br/><br/>V""",
    3: """K<br/><br/>{{c1::V}}""",
}

def main(
    template_nb: int,
    anchors_path: str = "./author_dir/combined_anchors.json",
    deck: str = "0_quotidien::Anchors",
    header: str = "Anchors",
    tags: str = "pro::meta::pegging_concept_medecine::anchors",
    ):
    """
    Convert anchor pairs from a JSON file into Anki flashcards.

    Parameters
    ----------
    template_nb : int
        Template number (1-3) defining the cloze deletion pattern
    anchors_path : str, optional
        Path to the JSON file containing anchor pairs
    deck : str, optional
        Name of the Anki deck to add cards to
    header : str, optional
        Header text to add to each card
    tags : str, optional
        Space-separated list of tags to add to each card
    
    Raises
    ------
    Exception
        If any flashcards fail to be added to Anki
    """
    anchors = json.loads(Path(anchors_path).read_text())
    assert anchors
    del anchors["__COMMENT"]

    template = TEMPLATES[template_nb]
    assert "K" in template and "V" in template, template
    assert template.count("K") == 1, template
    assert template.count("V") == 1, template
    assert "{{c1::" in template and "}}" in template.split("{{c1::", 1)[1], template

    tags = tags.split(" ")
    bodies = []
    for k, v in anchors.items():
        k = k.strip()
        if k != k.upper() and k == k.lower():
            k = k.title()
        v = v.strip()
        assert k, v
        assert v, k
        assert "}" not in k and "{" not in k, k
        assert "}" not in v and "{" not in v, v

        if template.index("K") < template.index("V"):
            body = template.replace("K", k, 1)[::-1].replace("V", v[::-1], 1)[::-1]
        else:
            body = template.replace("V", v, 1)[::-1].replace("K", k[::-1], 1)[::-1]
        assert k in body and v in body, body
        bodies.append(body)
    notes = [
        {
            "deckName": deck,
            "modelName": "Clozolkor",
            "fields": {
                "body": b,
                "header": header,
            },
            "tags": tags,
            "options": {"allowDuplicate": False},
        } for b in bodies
    ]

    res = call_anki(
        action="addNotes",
        notes=notes,
    )
    errors = [f"#{res.index(r)+1}/{len(res)}: {r}" for r in res if not str(r).isdigit()]
    results = [r for r in res if str(r).isdigit()]
    if len(results) != len(notes):
        raise Exception(f"Some flashcards were not added:{','.join(errors)}")



if __name__ == "__main__":
    fire.Fire(main)
