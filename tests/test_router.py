from app.services.router import route

CAD = {
    "glaucoma_probability": "0.82",
    "grade": "likely glaucoma",
    "cdr": "0.62",
    "quality": "gradable",
    "laterality": "OD",
}
NOTE = {
    "iop": "OD 22 mmHg",
    "age": "68",
    "prior_dx": "ocular hypertension",
    "medications": "latanoprost",
    "intolerances": "sulfa drugs",
    "comorbidities": "hypertension",
    "note_free_text": "68-year-old patient.",
    "unlisted_secret": "should reach nobody",
}


def test_pharmacist_never_sees_imaging_measurements():
    ctx = route(CAD, NOTE)["pharmacist"]
    for forbidden in ("cdr", "glaucoma_probability", "quality", "note_free_text"):
        assert forbidden not in ctx
    assert ctx["medications"] == "latanoprost"


def test_optometrist_has_no_pharmacy_facts():
    ctx = route(CAD, NOTE)["optometrist"]
    for forbidden in ("medications", "intolerances", "comorbidities"):
        assert forbidden not in ctx
    assert ctx["cdr"] == "0.62"


def test_ophthalmologist_has_no_medications():
    ctx = route(CAD, NOTE)["ophthalmologist"]
    assert "medications" not in ctx
    assert ctx["glaucoma_probability"] == "0.82"


def test_deny_by_default():
    for ctx in route(CAD, NOTE).values():
        assert "unlisted_secret" not in ctx