"""Generate the 4 CrimeGPT .docx templates (docxtpl / Jinja placeholders).

Binary .docx are committed, but this script is the reproducible source of truth.
Run from the repo root (or anywhere):  python templates/_build_templates.py

Placeholders use docxtpl syntax:
  {{ field }}                      scalar merge field
  {%tr for x in list %} … {%tr endfor %}   table-row loop (3-row pattern:
        a for-row and endfor-row that docxtpl deletes, wrapping the content row)
"""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

HERE = Path(__file__).resolve().parent

# Complex-script font for Gujarati/Devanagari text. Pinned so the rendered .docx never
# falls back to the viewer's default Indic font (which prints box glyphs where Noto is not
# the OS fallback). English/Latin text keeps its ORIGINAL face: only runs that actually
# contain Indic characters get Noto in the Latin (ascii/hAnsi) slots — Latin-only runs get
# Noto in the complex-script (w:cs) slot alone. The .ttf is bundled in fonts/ and must be
# installed on the demo machine — see README "Fonts".
GUJARATI_FONT = "Noto Sans Gujarati"
# OOXML w:rFonts holds ONE face per slot, so a CSS-style fallback list cannot live inside
# the document. The primary is pinned below; if it is not installed Word substitutes the
# next available face in this documented chain (all cover the Gujarati block U+0A80–U+0AFF).
FONT_FALLBACK_CHAIN = [GUJARATI_FONT, "Nirmala UI", "Shruti", "Arial Unicode MS"]

# Placeholders whose merged value is Gujarati/Hindi in a non-English doc. Their runs hold a
# Latin `{{ ... }}` tag at build time but render to Indic text, so they must be pinned as
# Indic even though _has_indic() sees only Latin now. This covers the LLM-translated
# narratives AND the identifier-embedding sentence fields assembled from the label dict.
INDIC_BOUND_FIELDS = (
    "proceedings_narrative",
    "investigation_done",
    "pending_investigation",
    "grounds_for_custody",
    "examination_purpose",
    "complaint_narrative",
    "seized_intro",
    "panch_intro",
    "accused_line",
    "remand_clause1",
    "med_body",
)


def _has_indic(text):
    """True if text has any Gujarati (U+0A80–U+0AFF) or Devanagari (U+0900–U+097F) char."""
    return any("ऀ" <= c <= "ॿ" or "઀" <= c <= "૿" for c in text)


def _pin_run(run):
    """Pin the Indic face on a run without disturbing Latin text.

    Indic run  -> all four slots (ascii/hAnsi/cs/eastAsia); belt-and-braces, since some
                  viewers route Indic text through the ascii slot. A run counts as Indic if
                  it already holds Indic characters OR holds a Gujarati-bound placeholder
                  that will render to Indic text.
    Latin run  -> only w:cs, so ascii/hAnsi keep the document's original Latin face.
    """
    text = run.text
    # Any `{{ L.* }}` label renders to Gujarati/Hindi, as do the sentence fields above and
    # any run already holding Indic characters.
    is_indic = (
        _has_indic(text)
        or "{{ L." in text
        or "L." in text and "{{" in text
        or any(field in text for field in INDIC_BOUND_FIELDS)
    )
    rfonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    if is_indic:
        for slot in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rfonts.set(qn(slot), GUJARATI_FONT)
    else:
        rfonts.set(qn("w:cs"), GUJARATI_FONT)


def _iter_runs(doc):
    """Yield every run in body paragraphs and (single-level) table cells."""
    for para in doc.paragraphs:
        yield from para.runs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    yield from para.runs


def _apply_fonts(doc):
    """Set the complex-script default to Noto and pin every run. Call once before saving.

    Only the complex-script (w:cs) default is changed, so even runs that docxtpl inserts
    at render time resolve Gujarati to Noto. The Latin (ascii/hAnsi) default is left
    untouched, so English keeps the document's original Latin face.
    """
    styles = doc.styles.element
    doc_defaults = styles.find(qn("w:docDefaults"))
    if doc_defaults is None:
        doc_defaults = OxmlElement("w:docDefaults")
        styles.insert(0, doc_defaults)
    rpr_default = doc_defaults.find(qn("w:rPrDefault"))
    if rpr_default is None:
        rpr_default = OxmlElement("w:rPrDefault")
        doc_defaults.append(rpr_default)
    rpr = rpr_default.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        rpr_default.append(rpr)
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)  # w:rFonts must be the first child of w:rPr
    # Complex-script default -> Noto (drop the theme ref so the explicit face wins).
    # ascii/hAnsi/eastAsia are left as-is, preserving the original Latin default.
    if rfonts.get(qn("w:cstheme")) is not None:
        del rfonts.attrib[qn("w:cstheme")]
    rfonts.set(qn("w:cs"), GUJARATI_FONT)

    for run in _iter_runs(doc):
        _pin_run(run)


def _title(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(14)
    return p


def _line(doc, text, bold=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = bold
    return p


def _looped_table(doc, headers, for_expr, content_cells, endfor="{%tr endfor %}"):
    """Build a table whose single content row repeats via docxtpl {%tr%}.

    Rows: [header] [for-tag] [content] [endfor-tag]. docxtpl removes the for/endfor
    rows and repeats the content row for each item.
    """
    n = len(headers)
    table = doc.add_table(rows=4, cols=n)
    table.style = "Table Grid"
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
        for r in table.rows[0].cells[i].paragraphs[0].runs:
            r.bold = True
    # for-row: tag in first cell, rest blank (docxtpl drops the whole row)
    table.rows[1].cells[0].text = for_expr
    # content-row: the repeated cells
    for i, c in enumerate(content_cells):
        table.rows[2].cells[i].text = c
    # endfor-row
    table.rows[3].cells[0].text = endfor
    return table


def _sig_block(doc, left_label, right_label):
    doc.add_paragraph()
    t = doc.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = left_label
    t.rows[0].cells[1].text = right_label
    t.rows[0].cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT


def _blank_box(doc, lines=3):
    """A single bordered cell with blank height — e.g. for a physical seal impression."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    cell.text = ""
    for _ in range(lines):
        cell.add_paragraph()
    return t


# --------------------------------------------------------------------------
def build_seizure_receipt():
    """CCTNS Form IF4 — Property Seizure Memo layout (uses existing pool fields only)."""
    doc = Document()
    _title(doc, "{{ L.heading_seizure }}")
    _line(doc, "{{ L.subtitle_seizure }}")
    doc.add_paragraph()

    # District / PS / Year / FIR header
    hdr = doc.add_table(rows=2, cols=2)
    hdr.style = "Table Grid"
    hdr.rows[0].cells[0].text = "{{ L.district }}: {{ district }}"
    hdr.rows[0].cells[1].text = "{{ L.police_station }}: {{ police_station }}"
    hdr.rows[1].cells[0].text = "{{ L.year }}: {{ fir_year }}    {{ L.fir_no }}: {{ fir_number }}"
    hdr.rows[1].cells[1].text = "{{ L.crime_case_no }}: {{ case_number }}    {{ L.fir_date }}: {{ fir_date }}"
    doc.add_paragraph()

    _line(doc, "{{ L.acts_sections }}: {{ acts_sections_line }}", bold=True)
    doc.add_paragraph()
    _line(doc, "{{ L.seizure_datetime_label }}: {{ seizure_datetime }}")
    _line(doc, "{{ L.seizure_place_label }}: {{ seizure_location }}")
    doc.add_paragraph()

    # Person from whom property seized
    _line(doc, "{{ L.person_seized_from }}", bold=True)
    _line(doc, "{{ L.name }}: {{ accused_name }}    {{ L.son_of }}: {{ accused_father }}    {{ L.age }}: {{ accused_age }}")
    _line(doc, "{{ L.address }}: {{ accused_address }}")
    doc.add_paragraph()

    # Identifier-embedding sentence assembled per-language in _build_context.
    _line(doc, "{{ seized_intro }}")
    # Seized-property table. (The est.-value column carries its own 'Rs.' prefix, so the
    # header drops the redundant '(Rs.)'.)
    _looped_table(
        doc,
        ["{{ L.col_sr }}", "{{ L.col_desc_property }}", "{{ L.col_qty }}", "{{ L.col_est_value }}"],
        "{%tr for item in seized_items %}",
        [
            "{{ loop.index }}",
            "{{ item.description }}",
            "{{ item.quantity }}",
            "{{ item.estimated_value }}",
        ],
    )
    doc.add_paragraph()

    # Two independent panch witness blocks
    _line(doc, "{{ L.indep_panch_label }}", bold=True)
    _line(doc, "1. {{ L.name }}: {{ witness1.full_name }}    {{ L.son_of }}: {{ witness1.father_name }}")
    _line(doc, "   {{ L.address }}: {{ witness1.address }}          {{ L.signature }}: ____________________")
    _line(doc, "2. {{ L.name }}: {{ witness2.full_name }}    {{ L.son_of }}: {{ witness2.father_name }}")
    _line(doc, "   {{ L.address }}: {{ witness2.address }}          {{ L.signature }}: ____________________")
    doc.add_paragraph()

    # Seizing / Investigating Officer signature block (rank + buckle number)
    _line(doc, "{{ L.seizing_officer_label }}", bold=True)
    _line(doc, "{{ L.name }}: {{ io_name }}    {{ L.rank }}: {{ io_rank }}    {{ L.buckle_no }}: {{ io_badge_no }}")
    _line(doc, "{{ L.police_station }}: {{ police_station }}          {{ L.signature }}: ____________________")
    doc.add_paragraph()
    _line(doc, "{{ L.note_draft }}")
    _apply_fonts(doc)
    doc.save(HERE / "seizure_receipt.docx")


def build_panchnama():
    doc = Document()
    _title(doc, "{{ L.heading_panchnama }}")
    doc.add_paragraph()
    _line(doc, "{{ L.police_station }}: {{ police_station }}    {{ L.district }}: {{ district }}")
    _line(doc, "{{ L.case_fir_no }}: {{ case_number }}  ({{ L.fir_no }} {{ fir_number }})")
    _line(doc, "{{ L.date }}: {{ panchnama_date }}    {{ L.place }}: {{ panchnama_place }}")
    doc.add_paragraph()
    _line(doc, "{{ panch_intro }}")
    _line(doc, "{{ L.panch_witnesses_label }}", bold=True)
    _looped_table(
        doc,
        ["{{ L.col_no }}", "{{ L.name }}", "{{ L.father_name }}", "{{ L.address }}"],
        "{%tr for w in witnesses %}",
        ["{{ loop.index }}", "{{ w.full_name }}", "{{ w.father_name }}", "{{ w.address }}"],
    )
    doc.add_paragraph()
    _line(doc, "{{ L.accused_label }}", bold=True)
    _line(doc, "{{ accused_line }}")
    doc.add_paragraph()
    _line(doc, "{{ L.narrative_label }}", bold=True)
    _line(doc, "{{ proceedings_narrative }}")
    doc.add_paragraph()
    _line(doc, "{{ L.articles_label }}", bold=True)
    _looped_table(
        doc,
        ["{{ L.col_no }}", "{{ L.col_description }}", "{{ L.col_quantity }}", "{{ L.col_est_value2 }}"],
        "{%tr for item in seized_items %}",
        ["{{ loop.index }}", "{{ item.description }}", "{{ item.quantity }}", "{{ item.estimated_value }}"],
    )
    doc.add_paragraph()
    _line(doc, "{{ L.panchnama_closing }}")
    _sig_block(doc, "{{ L.panch_sign_label }}", "{{ io_name }}\n{{ L.io_designation }}")
    _line(doc, "{{ L.note_draft }}")
    _apply_fonts(doc)
    doc.save(HERE / "panchnama.docx")


def build_remand_request():
    doc = Document()
    _line(doc, "{{ L.to }}")
    _line(doc, "{{ L.remand_court_line2 }}")
    _line(doc, "{{ district }}.")
    doc.add_paragraph()
    _title(doc, "{{ L.heading_remand }}")
    _line(doc, "{{ L.remand_subtitle }}")
    doc.add_paragraph()
    _line(doc, "{{ L.police_station }}: {{ police_station }}    {{ L.district }}: {{ district }}")
    _line(doc, "{{ L.case_fir_no }}: {{ case_number }}  ({{ L.fir_no }} {{ fir_number }} {{ L.dated }} {{ fir_date }})")
    doc.add_paragraph()
    _line(doc, "{{ L.respectfully }}", bold=True)
    _line(doc, "{{ remand_clause1 }}")
    _line(doc, "{{ L.remand_c2 }}")
    _looped_table(
        doc,
        ["{{ L.col_act }}", "{{ L.col_section }}", "{{ L.col_title }}"],
        "{%tr for s in sections_applied %}",
        ["{{ s.act }}", "{{ s.section_code }}", "{{ s.section_title }}"],
    )
    _line(doc, "{{ L.remand_c3 }}")
    _line(doc, "{{ investigation_done }}")
    _line(doc, "{{ L.remand_c4 }}")
    _line(doc, "{{ pending_investigation }}")
    _line(doc, "{{ L.remand_c5 }}")
    _line(doc, "{{ grounds_for_custody }}")
    doc.add_paragraph()
    _line(doc, "{{ L.remand_prayer }}")
    _sig_block(doc, "{{ L.place }}: {{ police_station }}", "{{ io_name }}\n{{ L.io_designation }}")
    _line(doc, "{{ L.note_draft }}")
    _apply_fonts(doc)
    doc.save(HERE / "remand_request.docx")


def build_medical_letter():
    doc = Document()
    _line(doc, "{{ L.to }}")
    _line(doc, "{{ L.medical_to2 }}")
    _line(doc, "{{ hospital }}.")
    doc.add_paragraph()
    _title(doc, "{{ L.heading_medical }}")
    doc.add_paragraph()
    _line(doc, "{{ L.from_label }} {{ io_name }}, {{ L.io_designation }}, {{ police_station }}, {{ district }}.")
    _line(doc, "{{ L.case_fir_no }}: {{ case_number }}  ({{ L.fir_no }} {{ fir_number }})")
    doc.add_paragraph()
    _line(doc, "{{ L.sir_madam }}")
    _line(doc, "{{ med_body }}")
    _line(doc, "{{ L.purpose_label }} {{ examination_purpose }}")
    doc.add_paragraph()
    _line(doc, "{{ L.med_closing }}")
    _sig_block(doc, "{{ L.place }}: {{ police_station }}", "{{ io_name }}\n{{ L.io_designation }}")
    _line(doc, "{{ L.note_draft }}")
    _apply_fonts(doc)
    doc.save(HERE / "medical_letter.docx")


# --------------------------------------------------------------------------
# LERS (Law Enforcement Response System) request templates — compliant request
# forms addressed to a platform (Meta / WhatsApp / Instagram). These are TEMPLATES,
# not a live API integration. They use only existing pool context fields; request-
# specific details (target identifier, data sought, date range, exact BNSS section)
# are blank fields the officer fills per request.
def _lers_common_header(doc, title):
    _title(doc, title)
    _line(doc, "{{ L.lers_compliant_note }}", bold=True)
    doc.add_paragraph()
    _line(doc, "{{ L.lers_to }}")
    _line(doc, "{{ L.lers_platform }} ____________________  (Meta / WhatsApp / Instagram)")
    doc.add_paragraph()
    _line(doc, "{{ L.lers_agency }} {{ police_station }}, {{ district }} (India)")
    _line(doc, "{{ L.case_fir_no }}: {{ case_number }}  ({{ L.fir_no }} {{ fir_number }} {{ L.dated }} {{ fir_date }})")
    _line(doc, "{{ L.lers_io }} {{ io_name }}, {{ io_rank }}, {{ L.lers_badge }} {{ io_badge_no }}")
    doc.add_paragraph()
    _line(doc, "{{ L.lers_legal_basis_a }}")
    _line(doc, "{{ L.lers_legal_basis_b }} {{ acts_sections_line }}.")
    doc.add_paragraph()
    _line(doc, "{{ L.lers_target }}", bold=True)
    _line(doc, "________________________________________________________________")
    doc.add_paragraph()


def _lers_footer(doc):
    doc.add_paragraph()
    _sig_block(
        doc,
        "{{ L.place }}: {{ police_station }}\n{{ L.date }}: ____________",
        "{{ io_name }}\n{{ io_rank }} · {{ L.buckle_no }} {{ io_badge_no }}\n{{ L.io_designation }}",
    )
    _line(doc, "{{ L.lers_note }}")


def build_lers_preservation_request():
    doc = Document()
    _lers_common_header(doc, "{{ L.lers_pres_heading }}")
    _line(doc, "{{ L.lers_pres_data }}", bold=True)
    _line(doc, "  [ ] {{ L.lers_opt_subscriber }}     [ ] {{ L.lers_opt_iphist }}")
    _line(doc, "  [ ] {{ L.lers_opt_metadata }}     [ ] {{ L.lers_opt_content }}")
    _line(doc, "  {{ L.lers_other }} ______________________________________________________")
    doc.add_paragraph()
    _line(doc, "{{ L.lers_pres_period }}")
    doc.add_paragraph()
    _line(doc, "{{ L.lers_pres_statement }}")
    _lers_footer(doc)
    _apply_fonts(doc)
    doc.save(HERE / "lers_preservation_request.docx")


def build_lers_records_request():
    doc = Document()
    _lers_common_header(doc, "{{ L.lers_rec_heading }}")
    _line(doc, "{{ L.lers_rec_data }}", bold=True)
    _line(doc, "  [ ] {{ L.lers_opt_basic }}     [ ] {{ L.lers_opt_iplogs }}")
    _line(doc, "  [ ] {{ L.lers_opt_txn }}     [ ] {{ L.lers_opt_stored }}")
    _line(doc, "  {{ L.lers_other }} ______________________________________________________")
    doc.add_paragraph()
    _line(doc, "{{ L.lers_rec_daterange }}")
    doc.add_paragraph()
    _line(doc, "{{ L.lers_rec_statement }}")
    _lers_footer(doc)
    _apply_fonts(doc)
    doc.save(HERE / "lers_records_request.docx")


def main():
    build_seizure_receipt()
    build_panchnama()
    build_remand_request()
    build_medical_letter()
    build_lers_preservation_request()
    build_lers_records_request()
    print("Built templates in", HERE)
    for f in sorted(HERE.glob("*.docx")):
        print("  -", f.name)


if __name__ == "__main__":
    main()
