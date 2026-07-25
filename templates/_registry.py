"""Document template registry (CLAUDE.md §8).

Maps a doc_type (matching models.enums.DocType values) to its Word template, a
human title, and the context fields that MUST be present for a meaningful document.

Adding a new document = drop a `.docx` into this folder + add ONE entry here.
No code change anywhere else. This is a Golden Hour seam (§10): a cyber freeze
letter is just another template + entry.

Kept import-free (no backend/app dependency) so it can be loaded by file path.
"""

REGISTRY = {
    "SEIZURE_RECEIPT": {
        "template_file": "seizure_receipt.docx",
        "title": "Seizure Receipt",
        "required_fields": [
            "case_number",
            "police_station",
            "io_name",
            "seizure_datetime",
            "seizure_location",
            "accused_name",
            "seized_items",
        ],
    },
    "PANCHNAMA": {
        "template_file": "panchnama.docx",
        "title": "Panchnama",
        "required_fields": [
            "case_number",
            "police_station",
            "io_name",
            "panchnama_date",
            "panchnama_place",
            "accused_name",
            "witnesses",
            "seized_items",
        ],
    },
    "REMAND": {
        "template_file": "remand_request.docx",
        "title": "Remand Request Letter (Police Custody)",
        "required_fields": [
            "case_number",
            "fir_number",
            "police_station",
            "accused_name",
            "sections_applied",
            "investigation_done",
            "pending_investigation",
            "grounds_for_custody",
        ],
    },
    "MEDICAL_LETTER": {
        "template_file": "medical_letter.docx",
        "title": "Medical Treatment / Examination Letter",
        "required_fields": [
            "case_number",
            "police_station",
            "io_name",
            "subject_name",
            "examination_purpose",
        ],
    },
    "CUSTODY_LETTER": {
        "template_file": "custody_letter.docx",
        "title": "Court Custody Letter (Judicial Custody)",
        "required_fields": [
            "case_number",
            "fir_number",
            "police_station",
            "accused_name",
            "sections_applied",
            "custody_clause1",
        ],
    },
    # Form I spine (items 1–9 + 15 + signatures). Items 10 / 11-col-7 / 16–19 reserved
    # in the template for a later pass — not required here.
    "CHARGESHEET": {
        "template_file": "chargesheet.docx",
        "title": "Final Form / Report (BNSS §193) — Form I",
        "required_fields": [
            "case_number",
            "fir_number",
            "fir_date",
            "police_station",
            "district",
            "acts_sections_line",
            "report_type",
            "accused_name",
            "brief_facts",
            "io_name",
            "sho_name",
        ],
    },
    "LERS_PRESERVATION_REQUEST": {
        "template_file": "lers_preservation_request.docx",
        "title": "LERS Data Preservation Request",
        "required_fields": [
            "case_number",
            "police_station",
            "district",
            "io_name",
        ],
    },
    "LERS_RECORDS_REQUEST": {
        "template_file": "lers_records_request.docx",
        "title": "LERS Records Disclosure Request",
        "required_fields": [
            "case_number",
            "police_station",
            "district",
            "io_name",
        ],
    },
}


def get_entry(doc_type: str) -> dict:
    """Return the registry entry for a doc_type, or raise KeyError with the valid set."""
    try:
        return REGISTRY[doc_type]
    except KeyError as exc:
        raise KeyError(
            f"Unknown doc_type {doc_type!r}. Registered: {sorted(REGISTRY)}"
        ) from exc
