# Legal Corpus — BNS / BNSS / BSA

Source: Gazette of India (Ministry of Law and Justice), official bare acts.
All three Acts received Presidential assent on 25 December 2023.

| Act  | Full name                                  | Sections |
|------|--------------------------------------------|----------|
| BNS  | Bharatiya Nyaya Sanhita, 2023              | 358      |
| BNSS | Bharatiya Nagarik Suraksha Sanhita, 2023   | 531      |
| BSA  | Bharatiya Sakshya Adhiniyam, 2023          | 170      |
| **Total** |                                       | **1059** |

## Files

- `<ACT>.txt` — cleaned full text (margin notes and page furniture removed)
- `<ACT>_sections.json` — section-level chunks
- `all_sections.jsonl` — all 1059 sections, one JSON object per line (use this for RAG ingest)

## Section record schema

```json
{
  "act": "BNS",
  "act_name": "Bharatiya Nyaya Sanhita, 2023",
  "section_code": "303",
  "title": "Theft",
  "text": "303. (1) Whoever, intending to take dishonestly ...",
  "char_len": 963,
  "citation": "BNS Section 303"
}
```

## Processing notes

Gazette pages carry marginal section titles that alternate between the left and
right margins by page. These were removed from the body text by cropping the page
to the body column (x 112–484pt) and captured separately as the `title` field, so
statutory text is free of margin bleed. Running headers, footers, page numbers and
rule lines were stripped.

Coverage was verified against the official section counts: every section from 1 to
the last in each Act is present, with no gaps.

A small number of sections (58) lost their margin-note title where cropping was too
aggressive, and three had a stray leading character bleed into the body text. These were
repaired by `data/backfill_section_titles.py`: blank titles were backfilled with a short
phrase derived from the first clause of the section text, and the leading-character bleeds
(BNS 44, BNSS 279, BNSS 401) were removed. No `title` was blank after this pass.

## Use in CrimeGPT

`all_sections.jsonl` is the retrieval corpus for the Legal Section Intelligence
module. Each section is one chunk; `citation` is what the UI displays so every AI
suggestion is traceable to real statutory text.
