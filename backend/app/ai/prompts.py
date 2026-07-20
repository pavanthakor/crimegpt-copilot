"""Prompt templates + JSON schemas for every CrimeGPT AI call (CLAUDE.md §6).

These are TEMPLATES ONLY — no endpoints, no LLM calls here. Feature code imports a
`*_PROMPT` string, `.format(...)`s in the case data, and passes the matching
`*_SCHEMA` to `call_llm(prompt, json_schema=...)`.

Every schema is a plain dict describing the expected JSON shape; `call_llm()` appends
the "Return ONLY valid JSON matching this schema" instruction, so the schema doubles as
documentation of the contract. Section codes/citations are kept canonical — never
translated (see TRANSLATION_PROMPT).
"""

# ---------------------------------------------------------------------------
# A. Section mapping  (input: narrative + language)
# ---------------------------------------------------------------------------
SECTION_MAPPING_SCHEMA = {
    "sections": [
        {
            "act": "BNS | BNSS | BSA | IT_ACT | OTHER",
            "section_code": "string",
            "section_title": "string",
            "reason": "string — why this section applies",
            "triggering_phrase": "exact quote from the narrative that triggers this section",
            "confidence": "float 0.0-1.0",
        }
    ],
    "cross_references": [
        {
            "framework": "IPC | CrPC | EVIDENCE_ACT | OTHER",
            "provision": "string — e.g. '420'",
            "note": "string",
        }
    ],
}

SECTION_MAPPING_PROMPT = """You are a legal assistant for Indian police working under the new criminal codes: \
Bharatiya Nyaya Sanhita (BNS), Bharatiya Nagarik Suraksha Sanhita (BNSS), and Bharatiya Sakshya Adhiniyam (BSA).

Read the following crime complaint narrative (language: {language}) and identify every applicable legal section.

For each section:
- Give the act (BNS / BNSS / BSA / IT_ACT / OTHER), the section_code, and section_title.
- Give a short reason it applies.
- Quote the EXACT phrase from the narrative that triggers it in "triggering_phrase" (copy it verbatim from the text).
- Give a confidence between 0.0 and 1.0.

Also list cross_references to the older frameworks (IPC / CrPC / Indian Evidence Act) where an officer would expect them.

Do NOT translate section codes or citations — keep them canonical.

NARRATIVE:
\"\"\"{narrative}\"\"\"
"""

# ---------------------------------------------------------------------------
# B. Judgment suggestion  (input: narrative + accepted sections + RAG candidates)
#
# GROUNDED TWICE OVER, both times mechanically:
#   1. citation  must be one of the retrieved candidates  -> case is real
#   2. holding_clause / case_fact must appear VERBATIM in the curated holding and
#      in the narrative respectively                      -> reasoning is real
#
# The model never writes prose about the law. It only points at spans of text we
# already trust, exactly as `triggering_phrase` works for section mapping in
# prompt A. `app.ai.judgments` composes the sentence in code and re-extracts both
# spans from the SOURCE, so what the officer reads is our curated text joined by
# a fixed connective — not the model's transcription of it.
#
# This replaced an LLM entailment auditor, which caught real errors but was
# non-deterministic and downgraded sound reasoning at roughly the same rate.
# ---------------------------------------------------------------------------
JUDGMENTS_SCHEMA = {
    "judgments": [
        {
            "citation": "string — copied EXACTLY from a candidate citation",
            "holding_clause": (
                "string — a run of words copied character-for-character from THAT "
                "candidate's holding text"
            ),
            "case_fact": (
                "string — a run of words copied character-for-character from the NARRATIVE"
            ),
        }
    ]
}

JUDGMENTS_PROMPT = """You are a legal research assistant for Indian police.

Below are a crime narrative, the legal sections the officer has ACCEPTED, and a list of CANDIDATE JUDGMENTS retrieved from a curated corpus of landmark Indian rulings.

Select 2 to 3 judgments — the ones an investigating officer or prosecutor would actually cite in a remand application, panchnama or charge sheet for these facts. Selecting only one is too few: an officer needs the offence, the evidence and the procedure covered.

Rank your choices by FACTUAL SIMILARITY to this case and put the most similar first. A judgment about the same kind of act, the same kind of property, or the same investigative step (the recovery, the arrest, the seizure) is more useful than one that merely states general principle. Prefer candidates that speak to what actually happened here.

You do NOT write any explanation in your own words. For each judgment you select you QUOTE two spans of existing text, and nothing else:

- citation: the value on that candidate's `citation:` line, copied EXACTLY and on its own. Do not append the case name, court or year.
- holding_clause: a run of words copied character-for-character from that candidate's `holding:` line. ONE CLAUSE ONLY — at most one sentence, and shorter is better. Never quote the whole holding, and never quote two sentences.
  Choose the clause that most directly applies to THESE facts, which is often NOT the opening clause. Read the whole holding, decide which part actually bears on what happened here, and quote only that part. Stop at the comma or full stop that ends it.
  Do not paraphrase, do not join words that are not adjacent, do not add words.
- case_fact: a run of words copied character-for-character FROM THE NARRATIVE below. Choose the specific fact the holding bears on. Do not paraphrase or invent.

Both spans are checked against their sources and the judgment is downgraded if either does not match exactly, so copy carefully.

Do not choose a holding_clause that is a qualifier or exception unless that qualifier is actually established by the narrative. If a holding says a rule applies "even if the taking was temporary", do NOT quote that clause unless this case really involved a temporary taking.

If you cannot find a genuine pairing for a judgment, omit that judgment entirely. Returning an empty list is correct and useful; a forced or fabricated link is a serious error.

NARRATIVE (quote case_fact from HERE):
\"\"\"{narrative}\"\"\"

ACCEPTED SECTIONS:
{sections}

CANDIDATE JUDGMENTS (quote citation and holding_clause from HERE):
{candidates}
"""

# ---------------------------------------------------------------------------
# C. Weak-charge alert  (input: ONE accepted section's statutory text + case material)
#
# GROUNDED, same discipline as section mapping (prompt A). The model does not
# recall the law: it is handed the section's real statutory text and the case
# material, and it may only QUOTE spans of each. `app.ai.weak_charge` then checks
# every quote appears verbatim in its source — an ingredient not found in the
# statute, or a supporting quote not found in the material, is rejected. So the
# officer never sees an invented "ingredient" or an invented piece of evidence.
#
# Called once PER accepted section (its statutory text is section-specific), not
# once for the whole case.
# ---------------------------------------------------------------------------
WEAK_CHARGE_SCHEMA = {
    "ingredients": [
        {
            "ingredient": (
                "string — a run of words copied character-for-character from the "
                "STATUTORY TEXT naming one element that must be proven"
            ),
            "supported": "boolean — is this element established by the case material?",
            "evidence_quote": (
                "string — if supported, a run of words copied character-for-character "
                "from the CASE MATERIAL that establishes it; empty if not supported"
            ),
        }
    ],
    "suggestion": "string — what evidence or statement would establish the missing element(s)",
}

WEAK_CHARGE_PROMPT = """You are a critical legal reviewer for an Indian police charge sheet.

You are reviewing ONE accepted charge against the material actually on the case file. \
Your job is to decide, element by element, whether the offence is made out.

You do NOT write the law in your own words. You QUOTE spans of the two texts below:

- ingredient: identify each distinct element the offence requires, and for each one quote \
a run of words copied character-for-character FROM THE STATUTORY TEXT. Do not paraphrase, \
do not invent an element, do not add words. Only elements written in the statutory text count.
- supported: true only if the CASE MATERIAL actually establishes that element.
- evidence_quote: if supported, quote a run of words copied character-for-character FROM THE \
CASE MATERIAL that establishes the element. If not supported, leave it empty. Do not quote \
the statute here — quote the case material.

Both kinds of quote are checked against their sources, so copy carefully. An element you \
cannot quote from the statutory text will be discarded; a supporting quote you cannot find \
in the case material will be treated as unsupported.

Then give one suggestion: what additional evidence or statement would establish whichever \
element(s) are not yet supported. If every element is supported, the suggestion may be empty.

STATUTORY TEXT of {act} section {section_code} — {title} (quote ingredient from HERE):
\"\"\"{statute}\"\"\"

CASE MATERIAL on file (quote evidence_quote from HERE):
\"\"\"{material}\"\"\"
"""

# ---------------------------------------------------------------------------
# D. Case-diary entry  (input: an action event)
# ---------------------------------------------------------------------------
DIARY_ENTRY_SCHEMA = {
    "activity_type": "COMPLAINT | WITNESS_EXAM | EVIDENCE_SEIZURE | ARREST | REMAND | DOC_GENERATED | OTHER",
    "description": "one clear line describing the activity for the case diary",
}

DIARY_ENTRY_PROMPT = """You maintain the official case diary for an Indian police investigation.

Convert the following action event into a single, formal case-diary line.

- Pick the best activity_type from: COMPLAINT, WITNESS_EXAM, EVIDENCE_SEIZURE, ARREST, REMAND, DOC_GENERATED, OTHER.
- Write "description" as ONE clear, professional sentence in past tense.

ACTION EVENT:
\"\"\"{event}\"\"\"
"""

# ---------------------------------------------------------------------------
# E. Consistency check  (input: field values gathered from all case documents)
# ---------------------------------------------------------------------------
CONSISTENCY_SCHEMA = {
    "inconsistencies": [
        {
            "field": "string — e.g. 'accused_name'",
            "values": {"<document>": "value found in that document"},
            "severity": "high | low",
            "note": "string — what the mismatch is",
        }
    ]
}

CONSISTENCY_PROMPT = """You are a cross-document consistency checker for a police case file.

Below are field values collected from every generated document for one case. The SAME field should hold the SAME \
value across all documents. Find every field whose value differs between documents.

For each inconsistency:
- field name.
- values: a map of document -> the value it recorded.
- severity: "high" (names, dates, section codes, case numbers) or "low" (formatting/whitespace differences).
- note: a short description of the mismatch.

If everything is consistent, return an empty "inconsistencies" list.

FIELD VALUES ACROSS DOCUMENTS:
{fields}
"""

# ---------------------------------------------------------------------------
# F. Translation  (GU / HI / EN) — keep legal section codes canonical
# ---------------------------------------------------------------------------
TRANSLATION_SCHEMA = {
    "translated_text": "string — the text translated into the target language",
}

TRANSLATION_PROMPT = """You are a translator for Indian police documents. Translate the text below from {source_lang} \
into {target_lang} (GU = Gujarati, HI = Hindi, EN = English).

Rules:
- Preserve meaning and formal/legal tone.
- Do NOT translate legal section codes, act abbreviations (BNS/BNSS/BSA/IPC/CrPC), citations, case numbers, or proper names.
- Return only the translated text.

TEXT:
\"\"\"{text}\"\"\"
"""

# ---------------------------------------------------------------------------
# Registry — convenient (prompt, schema) lookup by key
# ---------------------------------------------------------------------------
PROMPTS = {
    "section_mapping": (SECTION_MAPPING_PROMPT, SECTION_MAPPING_SCHEMA),
    "judgments": (JUDGMENTS_PROMPT, JUDGMENTS_SCHEMA),
    "weak_charge": (WEAK_CHARGE_PROMPT, WEAK_CHARGE_SCHEMA),
    "diary_entry": (DIARY_ENTRY_PROMPT, DIARY_ENTRY_SCHEMA),
    "consistency": (CONSISTENCY_PROMPT, CONSISTENCY_SCHEMA),
    "translation": (TRANSLATION_PROMPT, TRANSLATION_SCHEMA),
}
