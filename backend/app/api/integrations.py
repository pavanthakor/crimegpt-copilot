"""Integration endpoints (CLAUDE.md §7 integrations, Tier-3 bonus).

    POST /api/cases/{id}/export/cctns   map case -> IIF payload, POST it to the mock CCTNS
                                        receiver, persist the response, return payload + id
    POST /api/integrations/cctns/mock   mock CCTNS ingest API (simulates the external system)

The export handler does a real HTTP round-trip to the local mock endpoint so the demo can
show a deployment-ready path; swapping the mock URL for a live CCTNS endpoint is all that
production needs.
"""
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.auth import require_role
from app.api.cases import _get_visible_case
from app.core.db import get_db
from app.models import AuditLog, CaseDiaryEntry, User
from app.models.enums import ActivityType, AuditAction, UserRole
from app.services.cctns import build_iif_payload, mock_receive

router = APIRouter(prefix="/api", tags=["integrations"])


@router.post("/integrations/cctns/mock")
def cctns_mock_receiver(payload: dict = Body(...)):
    """Local mock of the external CCTNS ingest API — mints a mock FIR id. Unauthenticated
    on purpose: it stands in for a third-party system, not a CrimeGPT user action."""
    return mock_receive(payload)


@router.post("/cases/{case_id}/export/cctns")
def export_cctns(
    case_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.IO, UserRole.SHO)),
):
    """Export a case to CCTNS as an IIF payload via the mock receiver; persist + audit."""
    case = _get_visible_case(db, user, case_id)
    payload = build_iif_payload(db, case, user)

    mock_url = str(request.base_url).rstrip("/") + "/api/integrations/cctns/mock"
    try:
        resp = requests.post(mock_url, json=payload, timeout=10)
        resp.raise_for_status()
        mock = resp.json()
    except Exception as exc:  # noqa: BLE001 — surface a clean 502 rather than a 500
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"CCTNS mock export failed: {exc}")

    fir_id = mock.get("cctns_fir_id")

    # Persist the response in the audit trail (durable + queryable; no new table per scope).
    db.add(
        AuditLog(
            case_id=case.id,
            entity_type="cctns_export",
            entity_id=case.id,
            action=AuditAction.CREATE,
            field_changes={
                "cctns_fir_id": fir_id,
                "status": mock.get("status"),
                "iif_payload": payload,
                "mock_response": mock,
            },
            performed_by=user.id,
        )
    )
    db.add(
        CaseDiaryEntry(
            case_id=case.id,
            entry_datetime=datetime.now(timezone.utc),
            activity_type=ActivityType.OTHER,
            description=f"Exported to CCTNS (mock); FIR registered as {fir_id}.",
            auto_generated=True,
            created_by=user.id,
        )
    )
    db.commit()

    return {"cctns_fir_id": fir_id, "mock_response": mock, "iif_payload": payload}
