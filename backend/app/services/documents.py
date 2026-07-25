"""Document generation engine (CLAUDE.md §8).

Gathers every field from the Unified Case Data Pool, merges it into a Word template
via docxtpl, and records the result (documents row + audit_log + DOC_GENERATED diary).

Adding a new document type needs only a template + a registry entry (templates/_registry.py)
— no change here. Free-text/narrative portions are drafted deterministically from pool
data for now; every output is a DRAFT the officer reviews before finalizing.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

from docxtpl import DocxTemplate
from sqlalchemy.orm import Session

from app import demo_cache
from app.core import runtime

from app.models import (
    AuditLog,
    Case,
    CaseDiaryEntry,
    Document,
    DocumentVersion,
    LegalSection,
    Person,
    SeizedItem,
    Statement,
    User,
)
from app.models.enums import (
    ActivityType,
    AccusedStatus,
    AuditAction,
    DocStatus,
    DocType,
    Language,
    LegalAct,
    PersonRole,
    SectionStatus,
    UserRole,
)

# Fields per doc type that still need machine translation. Now EMPTY: the document
# narratives that used to live here (panchnama proceedings, the remand investigation/
# pending/grounds clauses, the medical purpose) are no longer drafted in English and
# translated — they are deterministic per-language sentence templates in
# templates/_labels.py, assembled with verbatim identifiers in _build_context. Document
# generation therefore makes NO LLM call. Retained (empty) because app.demo_cache_build
# still imports it; a rebuild of the demo cache should build per-language contexts instead
# (see the note in generate_document).
_TRANSLATABLE_BY_DOC: dict[str, list[str]] = {
    "PANCHNAMA": [],
    "REMAND": [],
    "MEDICAL_LETTER": [],
    "SEIZURE_RECEIPT": [],
}

_LANG_ENUM = {"gu": Language.GU, "hi": Language.HI, "en": Language.EN}

# services/documents.py -> parents: [1]=app, [2]=backend, [3]=repo root
_APP_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = _REPO_ROOT / "templates"
STORAGE_DIR = _APP_DIR / "storage" / "documents"


def _load_registry() -> dict:
    """Load templates/_registry.py by path (it lives outside the backend package)."""
    spec = importlib.util.spec_from_file_location(
        "doc_registry", TEMPLATES_DIR / "_registry.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.REGISTRY


def _load_labels() -> dict:
    """Load templates/_labels.py by path -> {lang: {label_key: text}} (EN/HI/GU)."""
    spec = importlib.util.spec_from_file_location(
        "doc_labels", TEMPLATES_DIR / "_labels.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.LABELS


def _fmt_dt(dt: datetime | None) -> str | None:
    return dt.strftime("%d/%m/%Y at %H:%M hrs") if dt else None


def _fmt_date(dt) -> str | None:
    return dt.strftime("%d/%m/%Y") if dt else None


def _fmt_inr(value) -> str:
    """Format a rupee amount with Indian digit grouping and an 'Rs.' prefix.

    108000 -> 'Rs. 1,08,000'; 250 -> 'Rs. 250'; None/blank -> ''. Rupees are shown as whole
    numbers (the pool stores no paise), so the raw-float '108000.0' artefact never appears.
    """
    if value is None or value == "":
        return ""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) > 3:
        last3, rest = s[-3:], s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        s = ",".join(groups) + "," + last3
    return f"Rs. {sign}{s}"


def _first(persons: list[Person], role: PersonRole) -> Person | None:
    return next((p for p in persons if p.role == role), None)


_CHARGE_SHEET_ACTS = {LegalAct.BNS.value, LegalAct.BNSS.value, LegalAct.BSA.value}
_REPORT_TYPES = {"original", "supplementary"}


def _fmt_status_label(L: dict, status: AccusedStatus | None) -> str:
    if status is None:
        return ""
    return L.get(f"cs_status_{status.value}", status.value)


def _build_context(
    db: Session,
    case: Case,
    user: User,
    lang: str = "en",
    report_type: str = "original",
) -> dict:
    """Assemble the full merge context from the case pool. All JSON-safe.

    `lang` ('en'|'hi'|'gu') selects the boilerplate label set (`L`) and the language of
    the identifier-embedding sentence fields, so one template renders in any language.
    Identifiers (names, numbers, codes, dates) are substituted verbatim regardless of lang.

    `report_type` ('original'|'supplementary') drives Form I item 5 for CHARGESHEET.
    """
    labels_all = _load_labels()
    L = labels_all.get((lang or "en").lower(), labels_all["en"])
    persons = db.query(Person).filter(Person.case_id == case.id).order_by(Person.id).all()
    seized = db.query(SeizedItem).filter(SeizedItem.case_id == case.id).order_by(SeizedItem.id).all()
    statements = db.query(Statement).filter(Statement.case_id == case.id).all()
    accepted = (
        db.query(LegalSection)
        .filter(
            LegalSection.case_id == case.id,
            LegalSection.status == SectionStatus.ACCEPTED,
        )
        .order_by(LegalSection.id)
        .all()
    )

    accused = _first(persons, PersonRole.ACCUSED)
    victim = _first(persons, PersonRole.VICTIM)
    complainant = _first(persons, PersonRole.COMPLAINANT)
    witnesses = [p for p in persons if p.role == PersonRole.WITNESS]

    # Person id -> name for seized_from on the Form I property table.
    person_name = {p.id: (p.full_name or "") for p in persons}

    seized_items = [
        {
            "description": s.description,
            "quantity": s.quantity,
            # Pre-formatted for display (Indian grouping + Rs.), so the template renders
            # "Rs. 1,08,000" not the raw float "108000.0".
            "estimated_value": _fmt_inr(s.estimated_value),
        }
        for s in seized
    ]
    witnesses_ctx = [
        {"full_name": w.full_name, "father_name": w.father_name, "address": w.address}
        for w in witnesses
    ]
    sections_applied = [
        {"act": s.act.value, "section_code": s.section_code, "section_title": s.section_title}
        for s in accepted
    ]

    # Seizure header derives from the first seized item (per-item in the pool).
    first_seized = seized[0] if seized else None

    # Medical subject: accused first, then victim, then complainant.
    subject = accused or victim or complainant
    subject_role = (
        "accused" if subject is accused and accused
        else "victim" if subject is victim and victim
        else "complainant" if subject else None
    )

    district = case.district or ""
    # Numbered, semicolon-separated so item boundaries stay clear even though individual
    # descriptions contain commas (e.g. "Gold chain, approx 18 grams, yellow metal").
    _descs = [s.description for s in seized if s.description]
    item_list = "; ".join(f"({i}) {d}" for i, d in enumerate(_descs, 1)) or "nil"

    # CCTNS Form IF4 (Property Seizure Memo) fields — derived from existing pool data.
    _empty_witness = {"full_name": "", "father_name": "", "address": ""}
    witness1 = witnesses_ctx[0] if len(witnesses_ctx) > 0 else _empty_witness
    witness2 = witnesses_ctx[1] if len(witnesses_ctx) > 1 else _empty_witness
    acts_sections_line = ", ".join(
        f"{s['act']} {s['section_code']}" for s in sections_applied
    )
    fir_year = case.fir_date.year if case.fir_date else ""

    # Identifier-embedding boilerplate sentences: assembled per-language from the label
    # dict, with identifiers substituted verbatim (names stay exactly as in the pool).
    io_name_val = user.full_name or user.username
    acc_fmt = {
        "accused_name": (accused.full_name if accused else "") or "",
        "accused_father": (accused.father_name if accused else "") or "",
        "accused_age": (accused.age if accused else "") or "",
        "accused_address": (accused.address if accused else "") or "",
    }
    _role_key = {"accused": "role_accused", "victim": "role_victim",
                 "complainant": "role_complainant"}.get(subject_role)
    subject_role_label = L.get(_role_key, "") if _role_key else ""
    seized_intro = L["seized_intro_S"].format(io_name=io_name_val or "")
    panch_intro = L["panch_intro_S"].format(io_name=io_name_val or "")
    accused_line = L["accused_line_S"].format(**acc_fmt)
    remand_clause1 = L["remand_c1_S"].format(**acc_fmt)
    custody_clause1 = L["custody_c1_S"].format(**acc_fmt)
    med_body = L["med_body_S"].format(
        subject_name=(subject.full_name if subject else "") or "",
        subject_role=subject_role_label,
    )
    hospital = f"{L['hospital_civil']}, {district}" if district else L["hospital_govt"]

    # Document narrative sentences — assembled per-language from the label templates
    # (templates/_labels.py), identifiers substituted verbatim. Previously drafted in
    # English and machine-translated; that mistranslated "seized" as "looted" (લૂટ) in
    # Gujarati and truncated the Hindi, so these now never touch the LLM. Officer-entered
    # content (complaint narrative, statements, item descriptions) is rendered verbatim.
    accused_name_or_above = (accused.full_name if accused else None) or L["accused_named_above"]

    proceedings_narrative = L["panch_narrative_S"].format(case_number=case.case_number)

    _inv_parts = [
        L["remand_inv_fir_S"].format(
            fir_number=case.fir_number or "—",
            fir_date=_fmt_date(case.fir_date) or "—",
            police_station=case.police_station or "—",
        )
    ]
    if accused:
        _inv_parts.append(L["remand_inv_arrested_S"].format(accused_name=accused.full_name or ""))
    _inv_parts.append(L["remand_inv_seized_S"].format(item_list=item_list))
    _inv_parts.append(
        L["remand_inv_stmts_S"].format(statement_count=len(statements))
        if statements else L["remand_inv_stmts_progress"]
    )
    investigation_done = " ".join(_inv_parts)

    pending_investigation = L["remand_pending_S"]
    grounds_for_custody = L["remand_grounds_S"].format(accused_name=accused_name_or_above)

    examination_purpose = (
        L["med_purpose_accused_S"] if (subject is accused and accused)
        else L["med_purpose_general_S"]
    )

    # ---- Form I / CHARGESHEET spine fields (additive; unused by other templates) ----
    rt = (report_type or "original").lower().strip()
    if rt not in _REPORT_TYPES:
        rt = "original"
    report_type_line = (
        L["cs_report_supplementary"] if rt == "supplementary" else L["cs_report_original"]
    )
    cs_supp_note = L["cs_supp_note_S"] if rt == "supplementary" else ""

    # Property table (item 8): always ≥1 row so the table never collapses.
    na = L.get("cs_na", "NA")
    if seized:
        property_items = []
        for i, s in enumerate(seized, 1):
            from_whom = ""
            if s.seized_from and person_name.get(s.seized_from):
                from_whom = person_name[s.seized_from]
            elif s.seizure_location:
                from_whom = s.seizure_location
            desc = s.description or ""
            if s.quantity:
                desc = f"{desc} (qty {s.quantity})" if desc else f"qty {s.quantity}"
            property_items.append(
                {
                    "sr": str(i),
                    "description": desc or na,
                    "estimated_value": _fmt_inr(s.estimated_value) or na,
                    "recovered_from": from_whom or na,
                    "identified": na,
                    "disposal": na,
                }
            )
    else:
        property_items = [
            {
                "sr": na,
                "description": na,
                "estimated_value": na,
                "recovered_from": na,
                "identified": na,
                "disposal": na,
            }
        ]

    # Brief facts (item 15): complaint narrative + investigation summary, selected language.
    _brief_parts = []
    if case.complaint_narrative:
        _brief_parts.append(case.complaint_narrative.strip())
    if investigation_done:
        _brief_parts.append(investigation_done.strip())
    brief_facts = "\n\n".join(_brief_parts)

    # SHO for the forwarding signature (first SHO user in the system).
    sho = db.query(User).filter(User.role == UserRole.SHO).order_by(User.id).first()

    return {
        # boilerplate labels for the active language (template renders {{ L.key }})
        "L": L,
        # identifier-embedding sentences (assembled above, per language)
        "seized_intro": seized_intro,
        "panch_intro": panch_intro,
        "accused_line": accused_line,
        "remand_clause1": remand_clause1,
        "custody_clause1": custody_clause1,
        "med_body": med_body,
        # case
        "case_number": case.case_number,
        "title": case.title,
        "fir_number": case.fir_number,
        "fir_date": _fmt_date(case.fir_date),
        "police_station": case.police_station,
        "district": district,
        "incident_location": case.incident_location,
        "incident_datetime": _fmt_dt(case.incident_datetime),
        "complaint_narrative": case.complaint_narrative,
        # officer (IF4 signature block: rank + buckle/badge number)
        "io_name": user.full_name or user.username,
        "io_rank": user.rank or "",
        "io_badge_no": user.badge_no or "",
        # accused (shared)
        "accused_name": accused.full_name if accused else None,
        "accused_father": (accused.father_name if accused else None) or "",
        "accused_age": (accused.age if accused else None) or "",
        "accused_address": (accused.address if accused else None) or "",
        # lists
        "seized_items": seized_items,
        "witnesses": witnesses_ctx,
        "sections_applied": sections_applied,
        # seizure header
        "seizure_datetime": _fmt_dt(first_seized.seizure_datetime) if first_seized else None,
        "seizure_location": (first_seized.seizure_location if first_seized else None),
        # panchnama — dated to the case's incident/proceedings date (paired with
        # panchnama_place = incident_location), NOT the document-generation date.
        "panchnama_date": _fmt_date(
            case.incident_datetime.date()
            if case.incident_datetime
            else (case.fir_date or datetime.now(timezone.utc).date())
        ),
        "panchnama_place": case.incident_location or case.police_station,
        "proceedings_narrative": proceedings_narrative,
        # remand narratives (assembled from _labels.py above)
        "investigation_done": investigation_done,
        "pending_investigation": pending_investigation,
        "grounds_for_custody": grounds_for_custody,
        # medical
        "hospital": hospital,
        "subject_name": subject.full_name if subject else None,
        "subject_role": subject_role,
        "examination_purpose": examination_purpose,
        # CCTNS Form IF4 (Property Seizure Memo)
        "fir_year": fir_year,
        "acts_sections_line": acts_sections_line,
        "witness1": witness1,
        "witness2": witness2,
        # ---- Form I / CHARGESHEET ----
        "report_type": rt,
        "report_type_line": report_type_line,
        "cs_supp_note": cs_supp_note,
        "complainant_name": (complainant.full_name if complainant else None) or "",
        "property_items": property_items,
        "brief_facts": brief_facts or None,
        "sho_name": (sho.full_name if sho else None) or (sho.username if sho else None),
        "sho_rank": (sho.rank if sho else None) or "",
        "sho_badge_no": (sho.badge_no if sho else None) or "",
        # Form I item 9 accused particulars (new columns + existing)
        "accused_dob_or_year": (accused.dob_or_year if accused else None) or "",
        "accused_sex": (accused.gender if accused else None) or "",
        "accused_nationality": (accused.nationality if accused else None) or "",
        "accused_address_verified": (accused.address_verified if accused else None) or "",
        "accused_passport_no": (accused.passport_no if accused else None) or "",
        "accused_passport_issue_date": (
            (_fmt_date(accused.passport_issue_date) if accused else None) or ""
        ),
        "accused_passport_issue_place": (accused.passport_issue_place if accused else None) or "",
        "accused_religion": (accused.religion if accused else None) or "",
        "accused_sc_st_obc": (accused.sc_st_obc if accused else None) or "",
        "accused_occupation": (accused.occupation if accused else None) or "",
        "accused_provisional_criminal_no": (
            (accused.provisional_criminal_no if accused else None) or ""
        ),
        "accused_regular_criminal_no": (
            (accused.regular_criminal_no if accused else None) or ""
        ),
        "accused_arrest_date": (
            (_fmt_date(accused.arrest_date) if accused else None) or ""
        ),
        "accused_bail_release_date": (
            (_fmt_date(accused.bail_release_date) if accused else None) or ""
        ),
        "accused_forwarded_to_court_date": (
            (_fmt_date(accused.forwarded_to_court_date) if accused else None) or ""
        ),
        "accused_arrest_acts_sections": (
            (accused.arrest_acts_sections if accused else None) or ""
        ),
        "accused_surety_details": (accused.surety_details if accused else None) or "",
        "accused_previous_convictions": (
            (accused.previous_convictions if accused else None) or ""
        ),
        "accused_status_label": _fmt_status_label(
            L, accused.status_of_accused if accused else None
        ),
    }


def _snapshot_version(db: Session, doc: Document, editor_id: int) -> None:
    """Archive the document's current state into document_versions (history/traceability).

    The snapshot carries the full document state (status/language/timestamps + the exact
    generated_data) so the version-history endpoint can reconstruct each past version
    without the live row. Called before a regeneration or a finalize supersedes it.
    """
    db.add(
        DocumentVersion(
            document_id=doc.id,
            version=doc.version or 1,
            snapshot={
                "status": doc.status.value if doc.status else None,
                "language": doc.language.value if doc.language else None,
                "generated_at": doc.generated_at.isoformat() if doc.generated_at else None,
                "generated_by": doc.generated_by,
                "generated_data": doc.generated_data,
            },
            edited_by=editor_id,
        )
    )


def finalize_document(db: Session, doc: Document, user: User) -> Document:
    """DRAFT -> FINALIZED: archive the current state as a version, bump, audit + diary.

    Raises ValueError if the document is already finalized.
    """
    if doc.status == DocStatus.FINALIZED:
        raise ValueError("Document is already finalized")

    old_version = doc.version or 1
    old_status = doc.status.value if doc.status else None
    _snapshot_version(db, doc, user.id)  # record the (draft) version being finalized
    doc.status = DocStatus.FINALIZED
    doc.version = old_version + 1

    db.add(
        AuditLog(
            case_id=doc.case_id,
            entity_type="document",
            entity_id=doc.id,
            action=AuditAction.UPDATE,
            field_changes={
                "status": {"old": old_status, "new": DocStatus.FINALIZED.value},
                "version": {"old": old_version, "new": doc.version},
            },
            performed_by=user.id,
        )
    )
    db.add(
        CaseDiaryEntry(
            case_id=doc.case_id,
            entry_datetime=datetime.now(timezone.utc),  # finalisation happens now
            activity_type=ActivityType.OTHER,
            description=f"{doc.doc_type.value} finalized (v{doc.version}).",
            auto_generated=True,
            created_by=user.id,
        )
    )
    db.commit()
    db.refresh(doc)
    return doc


def _missing_required(context: dict, required: list[str]) -> list[str]:
    missing = []
    for field in required:
        val = context.get(field)
        if val is None or (isinstance(val, (str, list)) and len(val) == 0):
            missing.append(field)
    return missing


def generate_document(
    db: Session,
    case_id: int,
    doc_type: DocType,
    user: User,
    lang: str | None = None,
    report_type: str = "original",
) -> Document:
    """Generate one document for a case and persist it as a DRAFT.

    `lang` ('gu'|'hi'|'en') selects the output language: _build_context assembles every
    boilerplate narrative from the per-language label templates and substitutes identifiers
    verbatim, so there is no LLM/translation step in document generation.

    `report_type` ('original'|'supplementary') is used by CHARGESHEET Form I item 5;
    ignored by other document types.

    Raises ValueError with the missing field list rather than rendering blanks.
    """
    case = db.get(Case, case_id)
    if case is None:
        raise ValueError(f"Case {case_id} not found")

    registry = _load_registry()
    entry = registry.get(doc_type.value)
    if entry is None:
        raise ValueError(f"No template registered for doc_type {doc_type.value}")

    template_path = TEMPLATES_DIR / entry["template_file"]
    if not template_path.exists():
        raise ValueError(f"Template file not found: {template_path}")

    rt = (report_type or "original").lower().strip()
    if rt not in _REPORT_TYPES:
        raise ValueError(
            f"Invalid report_type {report_type!r}; expected one of {sorted(_REPORT_TYPES)}"
        )

    # Resolve language: explicit lang wins, else the case's complaint language.
    lang_key = (lang or "en").lower()
    doc_language = _LANG_ENUM.get(lang_key, case.complaint_language)

    # DEMO_MODE (runtime-toggleable): serve the pre-generated context if present. Document
    # generation is deterministic now, so a miss simply falls through to the live build below.
    context = (
        demo_cache.load_document(case_id, doc_type.value, lang_key)
        if runtime.get_demo_mode() else None
    )
    if context is None:
        # Fully deterministic: _build_context assembles every narrative from the
        # per-language label templates (templates/_labels.py), so document generation makes
        # no LLM call and needs no translation pass. Officer-entered content (complaint
        # narrative, statements, item descriptions) is rendered verbatim.
        context = _build_context(
            db, case, user, lang=lang_key, report_type=rt
        )

    # Form I item 3: BNS / BNSS / BSA only — never IPC/CrPC / IT_ACT / OTHER on the sheet.
    if doc_type == DocType.CHARGESHEET:
        sections = [
            s for s in (context.get("sections_applied") or [])
            if s.get("act") in _CHARGE_SHEET_ACTS
        ]
        context["sections_applied"] = sections
        context["acts_sections_line"] = ", ".join(
            f"{s['act']} {s['section_code']}" for s in sections
        )
        # Ensure report_type fields reflect the request even when DEMO_MODE served a cache.
        context["report_type"] = rt
        L = context.get("L") or {}
        context["report_type_line"] = (
            L.get("cs_report_supplementary", "")
            if rt == "supplementary"
            else L.get("cs_report_original", "")
        )
        context["cs_supp_note"] = (
            L.get("cs_supp_note_S", "") if rt == "supplementary" else ""
        )

    missing = _missing_required(context, entry["required_fields"])
    if missing:
        raise ValueError(
            f"Cannot generate {entry['title']}: missing required field(s): {', '.join(missing)}"
        )

    # Regeneration is version-aware: if a document of this type already exists on the
    # case, archive its current state and bump the SAME row to a new draft version rather
    # than silently creating a duplicate (CLAUDE.md §5/§8 — "never overwrite silently").
    existing = (
        db.query(Document)
        .filter(Document.case_id == case_id, Document.doc_type == doc_type)
        .order_by(Document.id.desc())
        .first()
    )
    if existing is not None:
        _snapshot_version(db, existing, user.id)
        existing.version = (existing.version or 1) + 1
        existing.generated_data = context
        existing.language = doc_language
        existing.status = DocStatus.DRAFT
        existing.generated_by = user.id
        existing.generated_at = datetime.now(timezone.utc)
        doc = existing
    else:
        doc = Document(
            case_id=case_id,
            doc_type=doc_type,
            version=1,
            status=DocStatus.DRAFT,
            generated_data=context,
            language=doc_language,
            generated_by=user.id,
        )
        db.add(doc)
    db.flush()  # assign / confirm doc.id for a collision-free filename
    new_version = doc.version or 1

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STORAGE_DIR / f"{doc.id}_{doc_type.value}.docx"
    tpl = DocxTemplate(str(template_path))
    tpl.render(context)
    tpl.save(str(out_path))
    doc.file_path = str(out_path)

    db.add(
        AuditLog(
            case_id=case_id,
            entity_type="document",
            entity_id=doc.id,
            action=AuditAction.CREATE if new_version == 1 else AuditAction.UPDATE,
            field_changes={
                "doc_type": doc_type.value,
                "version": new_version,
                "status": "DRAFT",
            },
            performed_by=user.id,
        )
    )
    verb = "generated" if new_version == 1 else f"regenerated (v{new_version})"
    db.add(
        CaseDiaryEntry(
            case_id=case_id,
            entry_datetime=datetime.now(timezone.utc),  # generation happens now
            activity_type=ActivityType.DOC_GENERATED,
            description=f"{entry['title']} {verb} (draft).",
            auto_generated=True,
            created_by=user.id,
        )
    )

    db.commit()
    db.refresh(doc)
    return doc
