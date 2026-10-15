ROLE_FACTS: dict[str, list[str]] = {
    "ophthalmologist": ["glaucoma_probability", "grade", "cdr", "quality", "laterality",
                        "iop", "exam_findings", "prior_dx", "age", "note_free_text"],
    "optometrist":     ["glaucoma_probability", "grade", "cdr", "quality", "laterality",
                        "iop", "exam_findings", "prior_dx", "age", "note_free_text"],
    "pharmacist":      ["grade", "laterality", "age", "iop", "prior_dx",
                        "medications", "intolerances", "comorbidities"],
}


def route(cad_facts: dict[str, str], note_facts: dict[str, str]) -> dict[str, dict[str, str]]:
    """Deny-by-default projection: a role sees a fact only if ROLE_FACTS lists it."""
    pool = {**cad_facts, **note_facts}
    return {
        role: {key: pool[key] for key in allowed if key in pool}
        for role, allowed in ROLE_FACTS.items()
    }