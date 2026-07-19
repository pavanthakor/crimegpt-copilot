"""CCTNS/BharatPol mock export (CLAUDE.md §7 integrations, §11 services/cctns_mock).

Maps a case to a CCTNS IIF-style payload (IIF-1 case header + IIF-4 property-seizure
block) and provides the *mock* CCTNS receiver that mints a mock FIR id. There is no live
CCTNS — this simulates the ingest so the demo can show a deployment-ready export path.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Case, LegalSection, Person, SeizedItem, User
from app.models.enums import PersonRole, SectionStatus


def _iso_dt(dt) -> str | None:
    return dt.isoformat() if dt else None


def _iso_date(d) -> str | None:
    return d.isoformat() if d else None


def _person_brief(p: Person | None) -> dict | None:
    if p is None:
        return None
    return {
        "name": p.full_name,
        "father_name": p.father_name,
        "alias": p.alias,
        "age": p.age,
        "gender": p.gender,
        "address": p.address,
        "phone": p.phone,
    }


def build_iif_payload(db: Session, case: Case, user: User) -> dict:
    """Assemble the CCTNS IIF payload (IIF-1 case header + IIF-4 seizure block)."""
    persons = db.query(Person).filter(Person.case_id == case.id).order_by(Person.id).all()
    seized = db.query(SeizedItem).filter(SeizedItem.case_id == case.id).order_by(SeizedItem.id).all()
    accepted = (
        db.query(LegalSection)
        .filter(LegalSection.case_id == case.id, LegalSection.status == SectionStatus.ACCEPTED)
        .order_by(LegalSection.id)
        .all()
    )

    accused = next((p for p in persons if p.role == PersonRole.ACCUSED), None)
    complainant = next((p for p in persons if p.role == PersonRole.COMPLAINANT), None)
    witnesses = [p for p in persons if p.role == PersonRole.WITNESS]

    return {
        "iif_version": "1.0",
        "source_system": "CrimeGPT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "IIF-1": {  # Case / FIR header
            "district": case.district,
            "police_station": case.police_station,
            "fir_no": case.fir_number,
            "fir_date": _iso_date(case.fir_date),
            "fir_year": case.fir_date.year if case.fir_date else None,
            "crime_no": case.case_number,
            "case_type": case.case_type.value if case.case_type else None,
            "acts_sections": [
                {"act": s.act.value, "section": s.section_code, "title": s.section_title}
                for s in accepted
            ],
            "occurrence": {
                "datetime": _iso_dt(case.incident_datetime),
                "location": case.incident_location,
            },
            "complainant": _person_brief(complainant),
            "accused": [_person_brief(p) for p in persons if p.role == PersonRole.ACCUSED],
        },
        "IIF-4": {  # Property seizure block
            "seizure_datetime": _iso_dt(seized[0].seizure_datetime) if seized else None,
            "seizure_location": seized[0].seizure_location if seized else None,
            "seized_from": _person_brief(accused),
            "properties": [
                {
                    "sr": i + 1,
                    "description": s.description,
                    "quantity": s.quantity,
                    "estimated_value": float(s.estimated_value) if s.estimated_value is not None else None,
                }
                for i, s in enumerate(seized)
            ],
            "witnesses": [
                {"name": w.full_name, "father_name": w.father_name, "address": w.address}
                for w in witnesses
            ],
            "seizing_officer": {
                "name": user.full_name or user.username,
                "rank": user.rank,
                "buckle_no": user.badge_no,
            },
        },
    }


def mock_receive(payload: dict) -> dict:
    """Mock CCTNS receiver: minimally validate the IIF payload and mint a mock FIR id."""
    iif1 = payload.get("IIF-1", {}) if isinstance(payload, dict) else {}
    year = iif1.get("fir_year") or "0000"
    ref = uuid.uuid4().hex[:6].upper()
    fir_id = f"CCTNS-GJ-{year}-{ref}"
    return {
        "status": "ACCEPTED",
        "cctns_fir_id": fir_id,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "message": f"IIF payload accepted by CCTNS mock; FIR registered as {fir_id}.",
    }
