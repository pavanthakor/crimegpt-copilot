# CrimeGPT — User Guide (for Officers)

This guide explains how to use CrimeGPT to register a case, add its details once, and let
the system prepare your documents, suggest the correct legal sections, and keep everything
consistent. No technical knowledge is needed — just follow the steps.

The golden rule: **enter each fact once.** Every document you generate is built from what
you enter, so you never re‑type a name, date or seized item.

---

## 1. Sign in

1. Open CrimeGPT in your browser.
2. Enter your **username** and **password** and select **Sign in**.
3. What you can do depends on your role:
   - **Investigating Officer (IO)** — create and edit cases, add case data and evidence, run
     the AI, and generate documents.
   - **Station House Officer (SHO)** — everything an IO can see, across all officers, plus
     **approving (finalizing)** documents.
   - **Legal Advisor** — review a case's legal sections and judgments; cannot change evidence.

*Demo logins:* IO `io / io123`, SHO `sho / sho123`, Legal Advisor `legal / legal123`.

---

## 2. Create a case from the complaint

1. Select **New Case**.
2. Fill in the basics: case number, FIR number and date, police station, district, date and
   place of the incident.
3. Paste or type the **complaint narrative** in the complainant's own words. You can write in
   **Gujarati, Hindi or English** — choose the complaint language.
4. Save. The case is now registered and appears in your case list. This first save is also
   written to the case diary automatically.

---

## 3. Add the people and the evidence

Open the case and use its tabs to build the shared record.

**Persons.** Add everyone connected to the case — complainant, accused, witnesses, victim.
For each person record the name, father's name, age, address and phone where known. These
people flow into every document, so enter them carefully once.

**Seized items.** Add each seized article with its description, quantity, estimated value,
and from whom and where it was seized.

**Evidence files.** Upload photographs or documents. CrimeGPT automatically records a unique
digital fingerprint (a hash) for each file, so you can later prove it was not altered, and
lets you add tags to describe it.

**Statements.** Record witness or accused statements against the relevant person.

Everything you add here is the single source of truth the documents and the AI will use.

---

## 4. Analyse the legal sections

1. On the case, select **Analyse**.
2. CrimeGPT reads the complaint (and any statements) and suggests the **BNS sections** that
   apply. For each suggestion you will see:
   - the section number and title,
   - the **exact phrase from your complaint** that triggered it (highlighted), so you can see
     *why* it was suggested,
   - the old-law (IPC or CrPC) provision it replaces, where one exists.
3. The system only ever suggests **real sections from the law book** — it cannot invent a
   section. If a suggestion is not properly supported by the complaint text, it is dropped and
   shown separately so you can see what was rejected and why.
4. You can run the analysis in **Gujarati, Hindi or English** — the reason is shown in your
   chosen language, while the section numbers stay in their official form.

---

## 5. Accept (or reject) a section

Each suggested section is only a **draft** until you decide.

1. Review each suggestion and its triggering phrase.
2. Select **Accept** for the sections that apply, or **Reject** for those that do not.
3. Accepted sections are the ones that will appear on documents such as the Remand Request.

You are always in control — nothing is applied to a document until you accept it.

---

## 6. Generate documents

1. Open the **Documents** tab.
2. Choose the document to prepare. Eight are available:
   - **Property Seizure Receipt** (in the CCTNS Form IF4 layout)
   - **Accused Panchnama**
   - **Remand Request** (police custody)
   - **Court Custody Letter** (judicial custody)
   - **Medical Examination Letter**
   - **LERS Preservation Request** (ask a platform to preserve data)
   - **LERS Records Request** (ask a platform to disclose records)
   - **Final Form / Report** (BNSS §193), as an original or a supplementary report
3. CrimeGPT fills the document from the case record — persons, seized items, accepted
   sections, dates, your name, rank and buckle number — and produces a **draft** Word file.
4. **Download** the document to review and print it.

Because every document is built from the same record, the accused's name, the FIR number and
the seized items read the same on all of them.

### Switch language

When generating a document, pick the output language — **Gujarati, Hindi or English**. The
narrative portions are translated for you, while names, numbers, dates and section codes stay
exactly as recorded.

---

## 7. Read the case diary

Open the **Case Diary** on the case. CrimeGPT writes a dated, chronological entry every time
something important happens — the case is registered, the AI analysis is run, evidence is
added, a document is generated, or the case is exported. You get a ready‑made record of the
investigation's progress without writing it by hand. You can also add your own manual entries.

---

## 8. Search for a case

Use **Search** and type any of the following — CrimeGPT will find the matching cases and tell
you **what matched**:
- a case number or title,
- a word from the complaint,
- a **person's name** (complainant, accused or witness),
- a **seized item** description.

For example, searching an accused's name finds the case and shows that it matched on the
person's name.

---

## 9. View the audit trail

Open the **Audit** view on a case to see the complete, tamper‑evident history: who did what
and when — every create, update and delete, with the officer's name and rank, newest first.
You can filter it (for example, to only document actions). This is your accountability record.

---

## 10. Check consistency

Select **Consistency check**. CrimeGPT compares all the documents you have generated against
the current case record and against each other, and flags problems such as:
- a document that is **out of date** because the case changed after it was generated (for
  example, the accused's name was corrected later), and
- the same detail showing **different values** on different documents.

Each issue is marked **high** or **low** importance so you can fix the important ones before
anything goes to court.

---

## 11. Finalize a document

When a document has been reviewed and is correct, it can be **finalized** (approved) — this is
done by the **SHO**.

1. The SHO opens the document and selects **Finalize**.
2. Its status changes from **Draft** to **Finalized**, and a permanent snapshot of that
   version is saved.
3. You can view a document's **version history** at any time to see how it changed between
   versions and who approved it.

---

## In short

Enter the case once → add persons, evidence and items → analyse and accept the sections →
generate your documents in the language you need → check consistency → have the SHO finalize.
CrimeGPT keeps the diary, the audit trail and the version history for you.
