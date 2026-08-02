"""Case chat routing (CLAUDE.md §7).

    POST /api/cases/{case_id}/chat/route   one officer message -> an INTENT

THIS ENDPOINT CLASSIFIES AND STOPS. It opens no transaction, generates no document and
returns no prose. The caller takes the intent it hands back and calls the endpoint that
already does the work — for a document request, the very same
`POST /api/cases/{id}/documents/{doc_type}` the Documents tab uses.

Splitting it this way buys three things that matter:

  ONE GENERATION PATH. The chat cannot drift from the Documents tab, because it does not
  have its own way to make a document. There is nothing here to keep in step.

  A PLACE FOR THE GATE. Because routing and acting are separate calls, the officer's
  confirmation sits between them. Nothing is written on the strength of a classification.

  NO PROSE FROM THE MODEL. What comes back is a label out of a closed set. The sentence
  the officer reads is composed by the UI from its own translated strings, so the chat
  cannot state law, summarise a case, or volunteer an opinion — it has no channel to do
  it through.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.chat import (
    FILL_PLAN,
    classify_document_request,
    extract_field_answers,
    split_missing,
)
from app.api.auth import get_current_user
from app.api.cases import _get_visible_case
from app.core.db import get_db
from app.models import User

router = APIRouter(prefix="/api/cases", tags=["chat"])
logger = logging.getLogger("crimegpt.chat")


class ChatRouteRequest(BaseModel):
    message: str
    lang: str = "en"


class ChatRouteResponse(BaseModel):
    # A LABEL, not a sentence. GENERATE = one document identified; AMBIGUOUS = the words
    # fit more than one, so ask; UNKNOWN = not a document request we can serve.
    intent: str
    doc_type: str | None = None
    candidates: list[str] = []
    # Which stage decided — "alias" (deterministic table) or "model" (closed-set
    # fallback). Surfaced so a misroute can be diagnosed without re-running the request.
    source: str = "none"


@router.post("/{case_id}/chat/route", response_model=ChatRouteResponse)
def chat_route(
    case_id: int,
    body: ChatRouteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Classify one message. No side effects of any kind.

    The db session is here ONLY to enforce case visibility — an officer must not be able
    to probe the chat against a case they cannot see. Nothing is read from the case and
    nothing is written to it.
    """
    _get_visible_case(db, user, case_id)  # 404s an unknown or invisible case

    result = classify_document_request(body.message)
    logger.info(
        "chat route case=%s intent=%s doc_type=%s source=%s",
        case_id, result["intent"], result["doc_type"], result["source"],
    )
    return ChatRouteResponse(**result)


# ---------------------------------------------------------------------------
# Missing-field completion (capability 2)
# ---------------------------------------------------------------------------
class MissingSplitRequest(BaseModel):
    missing: list[str]


class MissingSplitResponse(BaseModel):
    # What the officer can answer here, what belongs to another surface, and anything
    # unrecognised — so the UI can say plainly which is which instead of asking for a
    # field no answer could ever fill.
    fillable: list[str] = []
    blocked: list[str] = []
    unknown: list[str] = []


@router.post("/{case_id}/chat/missing", response_model=MissingSplitResponse)
def chat_missing(
    case_id: int,
    body: MissingSplitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Split a generation checklist into answerable and not. Pure lookup, no side effects."""
    _get_visible_case(db, user, case_id)
    return MissingSplitResponse(**split_missing(body.missing))


class FieldAnswerRequest(BaseModel):
    answer: str
    fields: list[str]
    lang: str = "en"


class FieldAnswerResponse(BaseModel):
    # PROPOSED values, keyed by field. Nothing has been written; the officer confirms
    # these and the UI then calls the existing pool endpoints to apply them.
    values: dict[str, str] = {}
    # Asked for but not answered — these stay empty, and the document keeps blocking.
    unanswered: list[str] = []
    # Where each proposed value has to land: {"target": case|person|item, "field"|"role"}.
    # Sent from here rather than restated in the client, so the mapping from a document's
    # required field to the pool row behind it has exactly one definition (FILL_PLAN).
    plan: dict[str, dict] = {}


@router.post("/{case_id}/chat/answer", response_model=FieldAnswerResponse)
def chat_answer(
    case_id: int,
    body: FieldAnswerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Read an officer's reply onto the fields that were asked for. WRITES NOTHING.

    This is the same shape as intake's /extract: it proposes, the officer confirms, and
    the write happens through the pool endpoints that already exist. Keeping the read and
    the write in separate calls is what puts the confirmation gate between them.
    """
    _get_visible_case(db, user, case_id)
    asked = [f for f in body.fields if f in FILL_PLAN]
    values = extract_field_answers(body.answer, asked)
    unanswered = [f for f in asked if f not in values]
    logger.info(
        "chat answer case=%s asked=%s answered=%s", case_id, asked, sorted(values)
    )
    return FieldAnswerResponse(
        values=values,
        unanswered=unanswered,
        plan={f: FILL_PLAN[f] for f in values},
    )
