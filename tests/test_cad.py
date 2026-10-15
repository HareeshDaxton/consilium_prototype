import pytest

from app.schemas import RawVisionOutput
from app.services.cad import build_cad_context, cad_facts, grade, parse_note


@pytest.mark.parametrize("p,expected", [
    (0.0, "no glaucoma"),
    (0.19, "no glaucoma"),
    (0.2, "possible glaucoma"),
    (0.49, "possible glaucoma"),
    (0.5, "likely glaucoma"),
    (0.89, "likely glaucoma"),
    (0.9, "glaucoma detected"),
    (1.0, "glaucoma detected"),
])
def test_grade_boundaries(p, expected):
    assert grade(p) == expected


def test_cdr_passthrough():
    cad = build_cad_context(RawVisionOutput(glaucoma_probability=0.82, cdr=0.62, note="gradable"), "OD")
    assert cad.cdr == 0.62
    assert cad.grade == "likely glaucoma"
    facts = cad_facts(cad)
    assert facts["cdr"] == "0.62"
    assert facts["laterality"] == "OD"
    assert facts["quality"] == "gradable"


def test_missing_or_invalid_cdr_is_none():
    for bad in (None, 0.0, 1.7):
        cad = build_cad_context(RawVisionOutput(glaucoma_probability=0.5, cdr=bad))
        assert cad.cdr is None
        assert "CDR unavailable" in cad.quality_note
        assert "cdr" not in cad_facts(cad)


def test_parse_sample_note():
    note = ("68-year-old patient. IOP OD 22 mmHg. Prior dx: ocular hypertension. "
            "Medications: latanoprost. Intolerance: sulfa drugs.")
    facts = parse_note(note)
    assert facts["iop"] == "OD 22 mmHg"
    assert facts["age"] == "68"
    assert facts["prior_dx"] == "ocular hypertension"
    assert facts["medications"] == "latanoprost"
    assert facts["intolerances"] == "sulfa drugs"
    # pharmacist-only material must not leak through the free text
    assert "latanoprost" not in facts["note_free_text"]
    assert "sulfa" not in facts["note_free_text"]


def test_empty_note():
    assert parse_note(None) == {}
    assert parse_note("   ") == {}