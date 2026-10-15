from pydantic import BaseModel, Field


class CADResult(BaseModel):
    p_glaucoma: float                      # 0..1 from the vision endpoint
    grade: str                             # no glaucoma | possible glaucoma | likely glaucoma | glaucoma detected
    cdr: float | None = None               # cup-to-disc ratio; None if unusable
    quality_note: str                      # e.g. "image gradable" or flags
    laterality: str = "UNKNOWN"            # OD | OS | UNKNOWN


class RawVisionOutput(BaseModel):
    """Wire format from the friend's /predict endpoint (adapt in vision_client.py only)."""
    glaucoma_probability: float
    cdr: float | None = None               # computed server-side on his GPU
    masks_available: bool | None = None
    disc_mask_b64: str | None = None       # optional, unused in the prototype
    cup_mask_b64: str | None = None
    note: str | None = None


class SubReport(BaseModel):
    role: str                              # ophthalmologist | optometrist | pharmacist
    observations: str                      # prose, <= 250 words, role-scoped
    recommendations: str                   # prose, role-scoped
    uncertainties: str = ""


class Draft(BaseModel):
    impression: str
    findings: list[str]
    recommendations: list[str]
    disagreements: list[str] = Field(default_factory=list)   # preserved dissent
    caveats: list[str]                                        # must echo quality note + disagreements
    revision: int = 0


class Issue(BaseModel):
    kind: str                              # numeric_mismatch | unsupported | omission | unsafe_language
    detail: str


class Verdict(BaseModel):
    approved: bool
    issues: list[Issue] = Field(default_factory=list)


class FinalReport(BaseModel):
    case_id: str
    status: str                            # "verified" | "unverified_after_3_rounds"
    report_markdown: str
    draft: Draft
    cad: CADResult
    open_issues: list[Issue] = Field(default_factory=list)    # empty when verified


class GoogleLoginRequest(BaseModel):
    id_token: str