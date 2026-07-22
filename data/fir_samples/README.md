# FIR / Complaint Samples

These are **synthetic, fully anonymised** first-information-report / complaint samples,
provided as part of the CrimeGPT dataset deliverable (CLAUDE.md §13). They exist so the
document-generation and legal-section-mapping pipelines can be exercised against
realistic complaint text without using any real case data.

## What these are
- **Illustrative complaint narratives** written in the format of an Ahmedabad City Police
  FIR/complaint, covering three offence patterns not already in the seeded demo cases:
  1. `fir_sample_01_house_breaking.md` — house-breaking by night + theft in a dwelling
  2. `fir_sample_02_grievous_hurt.md` — voluntarily causing grievous hurt with a weapon
  3. `fir_sample_03_criminal_breach_of_trust.md` — criminal breach of trust by an employee
- They are **derived from the demo world** used by `backend/app/seed.py` (same districts and
  police stations — Satellite / Ellisbridge / Navrangpura, Ahmedabad) so they slot naturally
  alongside the two seeded cases (house-theft `I-CR-0142-2026`, vehicle-theft `I-CR-0199-2026`).

## Anonymisation & synthetic-data notice
- **Every name, address, phone number, vehicle registration, FIR number and identifier in these
  files is fictitious.** Any resemblance to a real person, case or FIR is coincidental.
- Phone numbers are masked (`XXXXXXXXXX`), house/flat numbers are generic, and complainant /
  accused names are invented.
- No real FIR text, victim data or case material was used to produce these samples.

## Legal-section references
The BNS (Bharatiya Nyaya Sanhita, 2023) sections listed in each sample are **illustrative**,
included because a real FIR carries them. They are a starting point for the section-mapping
demo, **not** a verified legal opinion — the officer confirms sections in the app (all AI
output is a reviewed draft, CLAUDE.md §0).

## Provenance
Synthetic, authored for this project. Free to use, modify and redistribute for the hackathon.
Pending: if the team supplies anonymised real-format samples, add them here and note their
source + anonymisation method in this README.
