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
# B. Judgment suggestion  (input: narrative + accepted sections)
# ---------------------------------------------------------------------------
JUDGMENTS_SCHEMA = {
    "judgments": [
        {
            "title": "string",
            "citation": "string",
            "court": "string",
            "summary": "string — <= 2 sentences, paraphrased, no copyrighted blocks",
            "relevance_reason": "string — why it matters to this case",
        }
    ]
}

JUDGMENTS_PROMPT = """You are a legal research assistant for Indian police.

Given the crime narrative and the legal sections the officer has ACCEPTED, suggest relevant Indian court judgments \
(Supreme Court / High Court) that an investigating officer or prosecutor would cite.

For each judgment:
- title, citation, court.
- A summary of at most 2 sentences, PARAPHRASED in your own words. Do not reproduce large blocks of the judgment text.
- relevance_reason: why it applies to this case.

Only suggest judgments you are reasonably confident are real. Keep citations canonical.

NARRATIVE:
\"\"\"{narrative}\"\"\"

ACCEPTED SECTIONS:
{sections}
"""

# ---------------------------------------------------------------------------
# C. Weak-charge alert  (input: narrative + accepted sections)
# ---------------------------------------------------------------------------
WEAK_CHARGE_SCHEMA = {
    "alerts": [
        {
            "section_code": "string",
            "missing_ingredients": ["string — legal ingredient not yet supported by facts"],
            "explanation": "string — why the charge is currently weak",
            "suggestion": "string — what evidence/statement would strengthen it",
        }
    ]
}

WEAK_CHARGE_PROMPT = """You are a critical legal reviewer for Indian police charge sheets.

Given the crime narrative and the ACCEPTED legal sections, check each section against its legal ingredients \
(the elements that must be proven). Flag any section where the narrative does NOT yet establish all ingredients.

For each weak/at-risk section:
- section_code.
- missing_ingredients: the specific elements not yet supported by the facts.
- explanation: why the charge is currently weak.
- suggestion: what additional evidence or statement would strengthen it.

If every section is well-supported, return an empty "alerts" list.

NARRATIVE:
\"\"\"{narrative}\"\"\"

ACCEPTED SECTIONS:
{sections}
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
