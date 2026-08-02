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

from app.ai.chat import classify_document_request
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
