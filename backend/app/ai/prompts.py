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
# G. Conversational intake extraction  (input: the officer's chat turns)
#
# PURE EXTRACTION — this prompt DECIDES NOTHING. It maps what the officer said onto
# the existing pool schema (cases / persons / seized_items, CLAUDE.md §5) and stops.
# It must never name a BNS/BNSS/BSA section, suggest a charge, or characterise an
# offence: section mapping is a separate, RAG-grounded, accept/reject flow (prompt A)
# and intake must not pre-empt or contaminate it.
#
# The guarantee is STRUCTURAL as well as instructional: `app.ai.intake` whitelists the
# returned keys against the pool schema, so any "sections"/"charges" field the model
# invents anyway is dropped before it can reach the officer.
# ---------------------------------------------------------------------------
INTAKE_EXTRACTION_SCHEMA = {
    # No title, police_station or district here on purpose. The title is composed in
    # code so it cannot pre-classify the offence, and the station/district describe where
    # the case is being REGISTERED — they come off the logged-in officer's record, not
    # out of what the complainant said.
    "case": {
        "incident_datetime": "string — ISO 8601 'YYYY-MM-DDTHH:MM:SS', or null",
        "incident_location": (
            "string — the place it happened: the locality, address or landmark the officer "
            "named. Fill this whenever the officer named any place at all. Null only if "
            "they named none"
        ),
        "complaint_narrative": "string — the incident as the officer described it",
        "fir_number": "string — ONLY if the officer stated one, else null",
    },
    "persons": [
        {
            "role": "COMPLAINANT | ACCUSED | WITNESS | VICTIM",
            "full_name": "string or null",
            "alias": "string or null",
            "father_name": "string or null",
            "age": "integer or null",
            "gender": "string or null",
            "address": "string or null",
            "phone": "string or null",
            "occupation": "string or null",
        }
    ],
    "seized_items": [
        {
            "description": "string — what the item is",
            "quantity": "integer or null",
            "estimated_value": "number or null",
            "seized_from_name": "string — the person's name it was seized from, or null",
            "seizure_datetime": "string — ISO 8601, or null",
            "seizure_location": "string or null",
        }
    ],
    "incident_described": (
        "boolean — true if the officer's words are an account of something that happened, "
        "even a very brief one; false if the text contains no account of any event"
    ),
    "reply": "string — one short sentence to the officer, in their language",
}

INTAKE_EXTRACTION_PROMPT = """You are a police records clerk taking down an incident report in India. \
Today's date is {today}.

Read the CONVERSATION below and extract ONLY the facts the officer actually stated, onto the \
record structure. You are a clerk filling in a form — you are NOT an investigator and NOT a lawyer.

STRICT RULES:
- Extract facts ONLY. Never state, name, cite or imply any legal section, act, charge or offence \
category (BNS, BNSS, BSA, IPC, IT Act or any other). Never say what crime this is. That decision \
belongs to the officer and to a separate legal-analysis step, not to you.
- Never invent, guess or infer a value. If the officer did not say it, use null. An empty record \
is correct; a plausible-sounding invention is a serious error.
- FIRST DECIDE ONE THING, before filling in anything: can you say WHAT HAPPENED — an act, done \
to some person or some thing? If you can name the act, set "incident_described" true. If you \
cannot, because the words name no act at all, set it false. Length is not the test: a handful of \
words can name an act, while a long run of letters or syllables that form no words in any language \
names none. Do not read an act into text that does not contain one.
- A REPORT CAN BE VERY SHORT AND STILL BE REAL. If the officer states that something happened — \
even in a handful of words, with no names, no date, no place and no property listed — that IS an \
incident: set "incident_described" true, fill in the little that is there, leave every other field \
null, and use "reply" to ask for the missing facts. Sparse is not the same as empty; do not discard \
a real report for being brief, and do not pad it out with details the officer never gave.
- IF THE CONVERSATION DESCRIBES NO INCIDENT AT ALL — it is blank, a greeting, a stray keystroke, \
random letters, or anything else that is not an account of something that happened — set \
"incident_described" false and return an EMPTY record: "persons": [], "seized_items": [], every \
case field null, and a "reply" asking the officer to describe the incident. Do NOT invent an \
incident, a name, an item or a place to fill the form. Returning nothing is the correct answer \
here, never a guess.
- Copy names, places and numbers EXACTLY as the officer gave them. Do not translate, transliterate \
or "correct" them.
- Write complaint_narrative in the SAME language the officer used ({language}), in their own words, \
as a plain factual account.
- Resolve relative dates ("yesterday", "last Tuesday", "this morning") against today's date, {today}.
- role must be exactly one of COMPLAINANT, ACCUSED, WITNESS, VICTIM. The person reporting the \
incident is COMPLAINANT. Someone harmed is VICTIM. Someone accused of the act is ACCUSED. Someone \
who saw it is WITNESS. If the officer did not make a person's role clear, leave that person out.
- ONE SENTENCE OFTEN NAMES TWO DIFFERENT PEOPLE — the person who saw something, and the person \
they saw doing it. List BOTH as separate entries. Whoever saw, heard or noticed the incident is a \
WITNESS even when the same sentence also names the person they were watching; do not drop the \
observer and keep only the actor.
- ATTACH EACH DETAIL TO THE NAME IT IS WRITTEN BESIDE. An age, occupation, address, father's name \
or phone number belongs to the nearest preceding name — the person it is written about — and never \
to a different person named later in the same sentence. If you are not certain which person a \
detail describes, leave it null rather than attaching it to the wrong person.
- fir_number is a LEGAL IDENTIFIER assigned by the police station. Fill it ONLY if the officer \
stated one in so many words. Never construct, guess, pattern-match or continue a number series to \
produce one — if the officer did not say it, it is null and it will be asked for.
- seized_from_name must be the name of a person you also listed in "persons", or null.
- "reply" is ONE short sentence in {language}: acknowledge what you recorded, and if a plain FACTUAL \
detail is missing (a name, a date, a place, an item), ask for that ONE detail. Ask about facts only — \
never about law, charges or what section applies. Do not summarise the law. Do not give advice.

CONVERSATION:
{conversation}
"""

# ---------------------------------------------------------------------------
# H. Document request routing  (input: one officer message)
#
# CLASSIFY ONLY. This prompt picks a label out of a closed set and returns nothing
# else — no prose, no summary, no advice. It is the fallback for phrasings the alias
# table in `app.ai.chat` does not already cover, so it runs on a minority of messages.
#
# The guarantee is structural, as with intake: the caller validates the returned value
# against the document REGISTRY and discards anything that is not an exact key. A model
# that invents a document type produces no effect at all, and a model that cannot decide
# produces a question to the officer rather than a guess.
# ---------------------------------------------------------------------------
DOC_REQUEST_SCHEMA = {
    "doc_type": (
        "exactly one of SEIZURE_RECEIPT, PANCHNAMA, REMAND, CUSTODY_LETTER, CHARGESHEET, "
        "MEDICAL_LETTER, LERS_PRESERVATION_REQUEST, LERS_RECORDS_REQUEST — or NONE"
    ),
    "query_kind": (
        "exactly one of EVIDENCE, WITNESSES, ACCUSED, PEOPLE, ITEMS, SECTIONS, DIARY, "
        "DOCUMENTS, STATEMENTS, STATUS — or NONE"
    ),
}

DOC_REQUEST_PROMPT = """You route messages in a police case-file assistant. \
The officer is either ASKING FOR A DOCUMENT to be prepared, or ASKING A QUESTION about \
what is already recorded in the case file. Decide which, and label it.

The documents are:
- SEIZURE_RECEIPT — receipt for property seized from a person (Form IF4)
- PANCHNAMA — the panchnama drawn up in front of panch witnesses
- REMAND — request to a court for POLICE custody of an arrested accused
- CUSTODY_LETTER — letter forwarding an accused to JUDICIAL custody
- CHARGESHEET — the final report / charge sheet to the court (Form I)
- MEDICAL_LETTER — letter asking a hospital to examine or treat a person
- LERS_PRESERVATION_REQUEST — asks a platform to PRESERVE data
- LERS_RECORDS_REQUEST — asks a platform to DISCLOSE records

The questions you can label are ONLY these, and each asks for something already recorded:
- EVIDENCE — what evidence has been collected
- WITNESSES — who the witnesses are
- ACCUSED — who the accused are
- PEOPLE — everyone recorded on the case
- ITEMS — what property has been seized
- SECTIONS — which legal sections have already been ACCEPTED on the case
- DIARY — the case diary entries
- DOCUMENTS — which documents have been generated
- STATEMENTS — the statements recorded
- STATUS — the case header: number, FIR, station, status

RULES:
- Answer with the labels alone. Write no sentence, no explanation, no legal comment.
- Set doc_type when they want a document PREPARED. Set query_kind when they are asking \
what the file already contains. Never set both.
- Set BOTH to NONE if the officer is asking anything else at all. This matters most for \
questions that ask you to JUDGE: whether the case is strong, whether someone is guilty, \
what they ought to charge, what will happen in court, what you advise. You do not answer \
those — you have no label for them, and NONE is the correct and expected answer. Do not \
reach for the nearest label because a question mentions evidence or charges.
- SECTIONS means "read back the sections already accepted", never "work out which \
sections apply". Deciding what applies is a different, reviewed step you take no part in.
- Never choose a label because it sounds important. Choose only what the words ask for.

OFFICER MESSAGE:
\"\"\"{message}\"\"\"
"""

# ---------------------------------------------------------------------------
# I. Missing-field answer  (input: the fields asked for + the officer's reply)
#
# The chat has told the officer which fields a document still needs and they have
# answered in their own words. This reads their answer onto those fields — and ONLY
# those fields, which the caller enforces with a whitelist built from the question it
# actually asked.
#
# THE POINT OF FAILURE HERE IS INVENTION, so the rule is the same one intake runs on: a
# field the officer did not answer stays null, and the caller additionally checks each
# value is traceable to the words they typed. An unanswered field must remain empty and
# block the document — a plausible-looking police station on a legal document is far
# worse than a document that refuses to generate.
# ---------------------------------------------------------------------------
FIELD_ANSWER_SCHEMA = {
    "values": {
        "<field_name>": "the value the officer gave for that field, or null",
    },
}

FIELD_ANSWER_PROMPT = """A police officer was asked to supply some missing details for a case \
file. Read their reply and match it to the fields that were asked for.

FIELDS ASKED FOR (use these names exactly, and no others):
{fields}

STRICT RULES:
- Return a value ONLY for a field the officer actually answered. If they did not mention a \
field, that field must be null. Leaving it null is correct and expected.
- Never invent, guess, complete or infer a value. Do not supply a plausible police station, \
date or name because one is missing — a wrong value on a legal document is far worse than a \
blank one, and a blank one simply gets asked for again.
- Copy what the officer wrote. Do not translate, transliterate, expand abbreviations or \
"correct" spellings of names and places.
- Dates: return ISO 8601 (YYYY-MM-DD, or YYYY-MM-DDTHH:MM:SS when a time was given). \
Resolve "yesterday" / "this morning" against today's date, {today}.
- Add no field that is not in the list above. Write no explanation, no legal comment and no \
sentence of any kind — return the values only.

OFFICER'S REPLY:
\"\"\"{answer}\"\"\"
"""

# ---------------------------------------------------------------------------
# K. Offence gate  (input: the complaint narrative)
#
# Asked ONCE, before any retrieval, so section selection never runs on text that alleges
# no offence. Refusal used to be emergent — an input was declined only when nothing
# survived grounding and the relevance floor — but retrieval always returns nearest
# neighbours and a similarity floor measures TOPICALITY, not criminality. An enquiry that
# merely shares vocabulary with an offence retrieves that offence above the floor.
#
# The question is deliberately STRUCTURAL, not topical: does the text report something
# that was DONE? A complaint contains a deed; a request for information contains none,
# whatever its subject. That distinction generalises, where any list of subjects would
# only ever fit the inputs it was written against.
#
# The model does not decide WHICH offence — only whether anything was done at all — and
# it must QUOTE the act, which `app.ai.legal` then checks against the narrative exactly
# as it checks a triggering_phrase. An offence asserted with no words to point at is not
# established.
# ---------------------------------------------------------------------------
OFFENCE_GATE_SCHEMA = {
    "alleges_offence": "boolean — true only if the text reports something that was DONE",
    "act_phrase": (
        "string — the words from the text naming what was done, copied EXACTLY "
        "character for character, or null if the text reports no act"
    ),
}

OFFENCE_GATE_PROMPT = """You screen incoming text for a police case system. Decide ONE thing: \
does this text REPORT SOMETHING THAT WAS DONE?

A report of an offence contains an ACT — something a person did, or tried to do, that wronged \
someone. A person acts with their WORDS as much as with their hands: threatening someone, \
demanding something by menace, inciting or urging another to act, and attempting or setting out \
to do any of these are all things a person DOES. When the act is words, the act is the SAYING of \
them — it is complete the moment they are spoken, and it does not matter whether the harm those \
words describe has happened, or ever happens at all. Words that announce a future harm are \
therefore a present act, not a future one.

Acts include: property taken, damaged, withheld or kept back; a person hurt, threatened, \
frightened, restrained or deceived; a document faked; money extracted or demanded under threat. \
The act may be recent or long past, the person who did it may be unknown, and the report may be \
very brief.

Text that reports NO act includes: a request for information or advice; a question about a \
procedure, a requirement, a fee or a timeline; an application, or an enquiry about one; a status \
check; an announcement, a greeting, or a message that simply passes on news. These describe \
wants, questions or states of affairs — not deeds.

RULES:
- Judge only what the words say. A subject that often appears in criminal matters is not itself \
an act: asking about a thing, or about the rules that govern it, is not the same as doing \
something to it or to someone.
- Never imagine an act the text does not describe, and never treat the mere mention of a topic \
as though something had been done.
- If the text reports an act, set alleges_offence true and copy into act_phrase the words from \
the text that name what was done — copied EXACTLY, character for character, from the text below.
- If it reports no act, set alleges_offence false and act_phrase null. False is a correct and \
expected answer, never a failure.
- Do not name any law, section or offence category. You are NOT deciding what offence this is — \
only whether anything was done at all.

TEXT:
\"\"\"{narrative}\"\"\"
"""

# ---------------------------------------------------------------------------
# Registry — convenient (prompt, schema) lookup by key
# ---------------------------------------------------------------------------
PROMPTS = {
    "offence_gate": (OFFENCE_GATE_PROMPT, OFFENCE_GATE_SCHEMA),
    "doc_request": (DOC_REQUEST_PROMPT, DOC_REQUEST_SCHEMA),
    "field_answer": (FIELD_ANSWER_PROMPT, FIELD_ANSWER_SCHEMA),
    "section_mapping": (SECTION_MAPPING_PROMPT, SECTION_MAPPING_SCHEMA),
    "intake_extraction": (INTAKE_EXTRACTION_PROMPT, INTAKE_EXTRACTION_SCHEMA),
    "judgments": (JUDGMENTS_PROMPT, JUDGMENTS_SCHEMA),
    "weak_charge": (WEAK_CHARGE_PROMPT, WEAK_CHARGE_SCHEMA),
    "diary_entry": (DIARY_ENTRY_PROMPT, DIARY_ENTRY_SCHEMA),
    "consistency": (CONSISTENCY_PROMPT, CONSISTENCY_SCHEMA),
    "translation": (TRANSLATION_PROMPT, TRANSLATION_SCHEMA),
}
