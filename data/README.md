# Data

Dataset deliverable (CLAUDE.md §13). Sources, licensing and anonymisation notes.

## `bns_bnss_bsa/`

Bare-act text of the Bharatiya Nyaya Sanhita, Bharatiya Nagarik Suraksha Sanhita and
Bharatiya Sakshya Adhiniyam. Public statutory text. Chunked one record per section and
embedded into the ChromaDB collection `legal_sections` (1059 documents).

    python -m app.ai.rag            # ingest (idempotent)
    python -m app.ai.rag --reset    # wipe and re-ingest

## `judgments/judgments.jsonl`

A curated corpus of 41 landmark Indian judgments covering the demo domain: theft and
recovery of stolen property, arrest and remand, electronic evidence, search and seizure,
panchnama practice, and witness credibility. Ingested into the **separate** ChromaDB
collection `judgments` so case law and chargeable sections never mix.

    python -m app.ai.judgments            # ingest (idempotent)
    python -m app.ai.judgments --reset    # wipe and re-ingest

One JSON object per line:

| field | notes |
|---|---|
| `case_title` | Party names as commonly cited |
| `citation` | Reporter citation, e.g. `(2014) 8 SCC 273` |
| `court` | Deciding court |
| `year` | Year of the decision |
| `holding` | **2–3 sentences, paraphrased in our own words.** No judgment text is reproduced |
| `relevance_tags` | Topic tags used for retrieval and filtering |
| `source_url` | Indian Kanoon search link for verification |

### Copyright

Holdings are original paraphrases written for this project, not extracts. This is
deliberate: CLAUDE.md §6 requires that we store "citations + short paraphrases only" and
never reproduce large blocks of copyrighted legal text. When the pipeline surfaces a
judgment to an officer it shows **the corpus holding, not a model-generated summary** —
`validate_judgments()` overwrites whatever the LLM wrote with the curated text, so the
officer never reads an AI paraphrase of a real case.

### ⚠️ Citations require verification before submission

The corpus was drafted from domain knowledge, not transcribed from a reporter. The cases
themselves are well-established landmarks, but **reporter volume and page numbers are the
most likely place for an error**, and a wrong citation in a remand application is a
serious defect.

Before the demo or any submission, each record's `citation` should be checked against its
`source_url` and corrected. `source_url` deliberately points at an Indian Kanoon *search*
rather than a specific document id, so a link never silently resolves to the wrong case.
Once verified, replacing it with the direct document URL is an improvement.

Two records are retained specifically because they are **no longer good law** — the
`overruled` / `overruled_in_part` tags mark them. They are kept so the retriever can
surface them with that caveat in the holding, rather than an officer citing them
unaware. Do not remove them without adjusting the holdings that reference them.

## `fir_samples/`

Anonymised FIR and document formats used to drive template accuracy. All names, phone
numbers, addresses and identifiers are replaced with fictional values.
