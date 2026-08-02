"""Seed demo users and the demo cases (CLAUDE.md §15). Safe to re-run (idempotent).

Run from backend/:  python -m app.seed

Deterministic by design: every value below is a literal — no now(), no random, no
faker. A fresh database + `alembic upgrade head` + `python -m app.seed` always
produces byte-identical demo content, so the demo starts from a known state.

The seed populates the pool (users, cases, persons, seized items, statements) plus
the case-diary history that led to each case's current state, with literal
timestamps. Case I-CR-0142-2026 also seeds ACCEPTED BNS legal sections so the
Form I chargesheet (BNSS §193) can generate end-to-end without a live analysis
pass. Documents and audit rows are still produced live by the demo flow.

Two cases, owned by two different IOs so the RBAC visibility rule (§9) is
demonstrable on the case list:
  I-CR-0142-2026  house theft   - owner `io`  - full pool, the demo centrepiece
  I-CR-0199-2026  vehicle theft - owner `io2` - lighter pool, status COMPLAINT
Logged in as `io` you see one case; as `sho` you see both.
"""
from datetime import date, datetime

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import (
    AuditLog,
    Case,
    CaseDiaryEntry,
    Document,
    DocumentVersion,
    Evidence,
    Judgment,
    LegalSection,
    Person,
    SeizedItem,
    Statement,
    User,
)
from app.models.enums import (
    ActivityType,
    AccusedStatus,
    CaseStatus,
    CaseType,
    Language,
    LegalAct,
    PersonRole,
    SectionStatus,
    StatementType,
    UserRole,
)

DEMO_USERS = [
    {
        "username": "io",
        "password": "io123",
        "full_name": "Inspector Rajesh Chauhan",
        "role": UserRole.IO,
        "rank": "Police Inspector",
        "badge_no": "GJ-AMD-4471",
        "police_station": "Satellite Police Station",
        "district": "Ahmedabad",
        # Step-up PIN, stored hashed (see _get_or_create_user). Plaintext here for the
        # same reason the passwords are: these are seeded demo credentials.
        "pin": "1234",
    },
    {
        # Deliberately posted to a DIFFERENT station from the other three: intake fills
        # the case header from whoever is logged in, and a constant would look identical
        # to a hardcoded value. Logging in as io2 is the proof it is officer-derived.
        "username": "io2",
        "password": "io2123",
        "full_name": "Sub-Inspector Meera Joshi",
        "role": UserRole.IO,
        "rank": "Police Sub-Inspector",
        "badge_no": "GJ-AMD-5518",
        "police_station": "Ellisbridge Police Station",
        "district": "Ahmedabad",
        "pin": "5678",
    },
    {
        "username": "sho",
        "password": "sho123",
        "full_name": "SHO Bhavna Desai",
        "role": UserRole.SHO,
        "rank": "Police Inspector (SHO)",
        "badge_no": "GJ-AMD-2210",
        "police_station": "Satellite Police Station",
        "district": "Ahmedabad",
        "pin": "4321",
    },
    {
        "username": "legal",
        "password": "legal123",
        "full_name": "Adv. Nikhil Mehta",
        "role": UserRole.LEGAL_ADVISOR,
        "rank": "Legal Advisor",
        "badge_no": "GJ-BAR-1187",
        "police_station": "Satellite Police Station",
        "district": "Ahmedabad",
        "pin": "8765",
    },
]

# Bilingual complaint narrative (Gujarati primary + English translation).
NARRATIVE_HOUSE_THEFT = (
    "ગુજરાતી: તારીખ ૧૦/૦૭/૨૦૨૬ ના રોજ રાત્રે આશરે ૦૨:૩૦ કલાકે, હું અને મારો પરિવાર "
    "ઊંઘમાં હતા ત્યારે કોઈ અજાણ્યા ઈસમે મારા ઘરની પાછળની બારીનો લોખંડનો કઠેડો તોડી "
    "ઘરમાં પ્રવેશ કર્યો હતો. તેણે કબાટમાંથી સોનાનો ચેન તથા રોકડ રૂ. ૨૫,૦૦૦ ચોરી "
    "કરી નાસી ગયો હતો. પાડોશી તથા સોસાયટીના ચોકીદારે શંકાસ્પદ ઈસમને ભાગતો જોયો હતો.\n\n"
    "English: On 10/07/2026 at about 02:30 hrs, while my family and I were asleep, "
    "an unknown person broke the iron grille of the rear window of my house and "
    "entered. He stole a gold chain and cash of Rs. 25,000 from the cupboard and "
    "fled. My neighbour and the society watchman saw the suspect running away."
)

NARRATIVE_VEHICLE_THEFT = (
    "On 15/07/2026 at about 22:45 hrs I parked my Honda Activa scooter "
    "(registration GJ-01-XX-1234) in the public parking at Law Garden and went "
    "into the market. On returning at about 23:30 hrs the scooter was missing "
    "from the parking. The parking attendant on duty saw an unknown young man "
    "push a scooter of the same description out of the parking towards "
    "Netaji Road and ride away on it."
)

# Explicit timestamps keep the case list order stable across reseeds
# (GET /cases sorts by created_at DESC, so the newer vehicle-theft case is on top).
# Each is after its own incident_datetime — a case cannot be registered before the
# offence it records.
CREATED_AT_HOUSE_THEFT = datetime(2026, 7, 10, 9, 15)
CREATED_AT_VEHICLE_THEFT = datetime(2026, 7, 16, 9, 20)

# Each case: the Case row, its people (keyed so items/statements can reference
# them), its seized items and its statements. Keys are seed-local only.
DEMO_CASES = [
    {
        "owner": "io",
        "case": {
            "case_number": "I-CR-0142-2026",
            "case_type": CaseType.CONVENTIONAL,
            "title": "House theft of gold ornaments and cash - Satellite, Ahmedabad",
            "fir_number": "0142/2026",
            "fir_date": date(2026, 7, 10),
            "police_station": "Satellite Police Station",
            "district": "Ahmedabad",
            "status": CaseStatus.INVESTIGATION,
            "incident_datetime": datetime(2026, 7, 10, 2, 30),
            "incident_location": "B/12 Shivalik Residency, Satellite, Ahmedabad",
            "complaint_narrative": NARRATIVE_HOUSE_THEFT,
            "complaint_language": Language.GU,
            "created_at": CREATED_AT_HOUSE_THEFT,
        },
        "persons": {
            "complainant": {
                "role": PersonRole.COMPLAINANT,
                "full_name": "Rameshbhai Patel",
                "father_name": "Manubhai Patel",
                "age": 52,
                "gender": "M",
                "address": "B/12 Shivalik Residency, Satellite, Ahmedabad",
                "phone": "9825012345",
                "occupation": "Shopkeeper",
            },
            "accused": {
                "role": PersonRole.ACCUSED,
                "full_name": "Suresh Vaghela",
                "alias": "Suri",
                "father_name": "Kanubhai Vaghela",
                "age": 27,
                "gender": "M",
                "address": "Vasna labour quarters, Ahmedabad",
                "phone": "9700098765",
                "occupation": "Daily-wage labourer",
                # Form I item 9 — enough for a complete CHARGESHEET spine.
                "dob_or_year": "1999",
                "nationality": "Indian",
                "address_verified": "Yes",
                "passport_no": None,
                "passport_issue_date": None,
                "passport_issue_place": None,
                "religion": "Hindu",
                "sc_st_obc": "No",
                "provisional_criminal_no": None,
                "regular_criminal_no": None,
                "arrest_date": date(2026, 7, 12),
                "bail_release_date": None,
                "forwarded_to_court_date": date(2026, 7, 13),
                "arrest_acts_sections": "BNS 303(2), BNS 331(3)",
                "surety_details": None,
                "previous_convictions": "Nil",
                "status_of_accused": AccusedStatus.FORWARDED,
            },
            "witness_neighbour": {
                "role": PersonRole.WITNESS,
                "full_name": "Kiran Shah",
                "father_name": "Dilipbhai Shah",
                "age": 45,
                "gender": "M",
                "address": "B/11 Shivalik Residency, Satellite, Ahmedabad",
                "phone": "9898011223",
                "occupation": "Neighbour / Businessman",
            },
            "witness_watchman": {
                "role": PersonRole.WITNESS,
                "full_name": "Prakash Rana",
                "father_name": "Govindbhai Rana",
                "age": 38,
                "gender": "M",
                "address": "Staff quarters, Shivalik Residency, Satellite",
                "phone": "9033044556",
                "occupation": "Society watchman",
            },
        },
        "seized_items": [
            {
                "description": "Gold chain, approx 18 grams, yellow metal",
                "quantity": 1,
                "estimated_value": 108000,
                "seized_from": "accused",
                "seizure_datetime": datetime(2026, 7, 12, 11, 0),
                "seizure_location": "Vasna, Ahmedabad",
            },
            {
                "description": "Iron crowbar used to break the window grille",
                "quantity": 1,
                "estimated_value": 250,
                "seized_from": "accused",
                "seizure_datetime": datetime(2026, 7, 12, 11, 0),
                "seizure_location": "Vasna, Ahmedabad",
            },
        ],
        "statements": [
            {
                "person": "witness_watchman",
                "statement_type": StatementType.WITNESS,
                "language": Language.EN,
                "statement_text": (
                    "On the night of 10/07/2026 at around 02:35 hrs I was on duty at "
                    "the main gate of Shivalik Residency. I saw a man of medium build "
                    "jump over the rear compound wall and run towards Vasna. I raised "
                    "an alarm and informed the residents."
                ),
            },
        ],
        # ACCEPTED BNS sections so Form I item 3 (acts_sections_line) resolves without
        # a live analysis pass. BNS only — never IPC/CrPC on the chargesheet.
        "legal_sections": [
            {
                "act": LegalAct.BNS,
                "section_code": "303(2)",
                "section_title": "Theft",
                "reason": "House-breaking and theft of gold ornament from dwelling.",
                "triggering_phrase": "gold chain",
                "confidence": 0.92,
                "status": SectionStatus.ACCEPTED,
            },
            {
                "act": LegalAct.BNS,
                "section_code": "331(3)",
                "section_title": "House-breaking",
                "reason": "Forced entry by breaking window grille of the residence.",
                "triggering_phrase": "broke the window grille",
                "confidence": 0.88,
                "status": SectionStatus.ACCEPTED,
            },
        ],
        # Investigation history up to the case's current state. Literal timestamps,
        # chronological, each matching the pool row it describes (the seizure entries
        # share the seized items' 11:00 timestamp, which exercises the id tiebreak in
        # the diary ordering).
        "diary": [
            {
                "entry_datetime": datetime(2026, 7, 10, 9, 15),
                "activity_type": ActivityType.COMPLAINT,
                "description": (
                    "Case I-CR-0142-2026 registered from FIR complaint No. 0142/2026 "
                    "at Satellite Police Station."
                ),
            },
            {
                "entry_datetime": datetime(2026, 7, 10, 11, 40),
                "activity_type": ActivityType.WITNESS_EXAM,
                "description": (
                    "Statement of society watchman Prakash Rana recorded under BNSS; "
                    "he saw the suspect flee towards Vasna."
                ),
                "person": "witness_watchman",
            },
            {
                "entry_datetime": datetime(2026, 7, 12, 10, 15),
                "activity_type": ActivityType.ARREST,
                "description": (
                    "Accused Suresh Vaghela apprehended at the Vasna labour quarters."
                ),
                "person": "accused",
            },
            {
                "entry_datetime": datetime(2026, 7, 12, 11, 0),
                "activity_type": ActivityType.EVIDENCE_SEIZURE,
                "description": (
                    "Gold chain (approx 18 grams) seized from the accused at Vasna "
                    "in the presence of panch witnesses."
                ),
                "person": "accused",
            },
            {
                "entry_datetime": datetime(2026, 7, 12, 11, 0),
                "activity_type": ActivityType.EVIDENCE_SEIZURE,
                "description": (
                    "Iron crowbar used to break the window grille seized from the "
                    "accused at Vasna."
                ),
                "person": "accused",
            },
        ],
    },
    {
        "owner": "io2",
        "case": {
            "case_number": "I-CR-0199-2026",
            "case_type": CaseType.CONVENTIONAL,
            "title": "Two-wheeler theft near Law Garden",
            "fir_number": "0199/2026",
            "fir_date": date(2026, 7, 15),
            "police_station": "Ellisbridge Police Station",
            "district": "Ahmedabad",
            "status": CaseStatus.COMPLAINT,
            "incident_datetime": datetime(2026, 7, 15, 22, 45),
            "incident_location": "Law Garden parking, Ahmedabad",
            "complaint_narrative": NARRATIVE_VEHICLE_THEFT,
            "complaint_language": Language.EN,
            "created_at": CREATED_AT_VEHICLE_THEFT,
        },
        "persons": {
            "complainant": {
                "role": PersonRole.COMPLAINANT,
                "full_name": "Nileshbhai Trivedi",
                "father_name": "Harshadbhai Trivedi",
                "age": 34,
                "gender": "M",
                "address": "A/7 Sarvottam Flats, Navrangpura, Ahmedabad",
                "phone": "9426078812",
                "occupation": "Bank clerk",
            },
            "accused": {
                "role": PersonRole.ACCUSED,
                "full_name": "Imran Shaikh",
                "alias": "Immu",
                "father_name": "Yusufbhai Shaikh",
                "age": 23,
                "gender": "M",
                "address": "Shahpur Darwaja, Ahmedabad",
                "phone": "9714455201",
                "occupation": "Garage helper",
            },
            "witness_attendant": {
                "role": PersonRole.WITNESS,
                "full_name": "Dinesh Solanki",
                "father_name": "Bhikhabhai Solanki",
                "age": 41,
                "gender": "M",
                "address": "Paldi, Ahmedabad",
                "phone": "9265533418",
                "occupation": "Parking attendant",
            },
        },
        "seized_items": [
            {
                "description": (
                    "Honda Activa scooter, registration GJ-01-XX-1234, "
                    "recovered without number plate"
                ),
                "quantity": 1,
                "estimated_value": 62000,
                "seized_from": "accused",
                "seizure_datetime": datetime(2026, 7, 17, 16, 30),
                "seizure_location": "Shahpur, Ahmedabad",
            },
        ],
        "statements": [
            {
                "person": "witness_attendant",
                "statement_type": StatementType.WITNESS,
                "language": Language.EN,
                "statement_text": (
                    "I am the attendant at the Law Garden public parking. On "
                    "15/07/2026 at about 23:00 hrs I saw a young man of thin build "
                    "push a white Honda Activa out of the parking towards Netaji "
                    "Road without showing a parking token. He started it a short "
                    "distance away and rode off. I can identify him if shown."
                ),
            },
        ],
        # Deliberately shorter than case 1 — this case is still at COMPLAINT stage.
        "diary": [
            {
                "entry_datetime": datetime(2026, 7, 16, 9, 20),
                "activity_type": ActivityType.COMPLAINT,
                "description": (
                    "Case I-CR-0199-2026 registered from FIR complaint No. 0199/2026 "
                    "at Ellisbridge Police Station."
                ),
            },
            {
                "entry_datetime": datetime(2026, 7, 16, 10, 5),
                "activity_type": ActivityType.WITNESS_EXAM,
                "description": (
                    "Statement of parking attendant Dinesh Solanki recorded; he can "
                    "identify the person who removed the scooter."
                ),
                "person": "witness_attendant",
            },
            {
                "entry_datetime": datetime(2026, 7, 17, 16, 30),
                "activity_type": ActivityType.EVIDENCE_SEIZURE,
                "description": (
                    "Honda Activa GJ-01-XX-1234 recovered and seized at Shahpur, "
                    "Ahmedabad."
                ),
                "person": "accused",
            },
        ],
    },
]

# The demo centrepiece — used as the default by demo_cache_build and preflight.
DEMO_CASE_NUMBER = DEMO_CASES[0]["case"]["case_number"]


def _get_or_create_user(db, data) -> tuple[User, bool]:
    user = db.query(User).filter(User.username == data["username"]).first()
    if user is not None:
        # Backfill officer attributes on already-seeded users (existing data survives).
        user.rank = data["rank"]
        user.badge_no = data["badge_no"]
        user.police_station = data["police_station"]
        user.district = data["district"]
        # Re-hashed on every seed run: bcrypt salts each call, so this is not idempotent
        # byte-for-byte, but the PIN it verifies is. Cheap, and it means an existing demo
        # database picks up the PIN without a manual step.
        user.pin_hash = hash_password(data["pin"])
        return user, False
    user = User(
        username=data["username"],
        password_hash=hash_password(data["password"]),
        full_name=data["full_name"],
        role=data["role"],
        rank=data["rank"],
        badge_no=data["badge_no"],
        police_station=data["police_station"],
        district=data["district"],
        pin_hash=hash_password(data["pin"]),
    )
    db.add(user)
    db.flush()
    return user, True


def _populate_children(db, case: Case, spec: dict, owner: User) -> None:
    """Insert the pool (persons, seized items, statements) and the seeded diary for `case`
    from its spec. Assumes the case row already exists and currently has no children
    (either a fresh create or a reset that just cleared them)."""
    people: dict[str, Person] = {}
    for key, fields in spec["persons"].items():
        person = Person(case_id=case.id, **fields)
        db.add(person)
        people[key] = person
    db.flush()

    for fields in spec["seized_items"]:
        fields = dict(fields)
        owner_key = fields.pop("seized_from", None)
        db.add(SeizedItem(
            case_id=case.id,
            seized_from=people[owner_key].id if owner_key else None,
            **fields,
        ))

    for fields in spec["statements"]:
        fields = dict(fields)
        person_key = fields.pop("person")
        db.add(Statement(
            case_id=case.id,
            person_id=people[person_key].id,
            recorded_by=owner.id,
            **fields,
        ))

    for fields in spec.get("diary", []):
        fields = dict(fields)
        person_key = fields.pop("person", None)
        db.add(CaseDiaryEntry(
            case_id=case.id,
            related_person_id=people[person_key].id if person_key else None,
            auto_generated=True,
            created_by=owner.id,
            **fields,
        ))

    for fields in spec.get("legal_sections", []):
        db.add(LegalSection(
            case_id=case.id,
            added_by=owner.id,
            **fields,
        ))


def _seed_case(db, spec: dict, owner: User) -> tuple[Case, bool]:
    """Create one case and its pool. Idempotent per case_number."""
    case_number = spec["case"]["case_number"]
    existing = db.query(Case).filter(Case.case_number == case_number).first()
    if existing is not None:
        return existing, False

    case = Case(**spec["case"], created_by=owner.id)
    db.add(case)
    db.flush()
    _populate_children(db, case, spec, owner)
    return case, True


# Every table that hangs off a case, deletable by a `case_id == cid` filter. Ordered so a
# child is removed before the parent it points at (persons last — items/statements/diary
# reference them). document_versions has no case_id (it references document_id) and is
# handled separately in _reset_case.
# Deletion order is FK-safe: the referencing rows go first, then the rows they point at.
# CaseDiaryEntry (related_person_id / related_evidence_id) and AuditLog must be deleted
# BEFORE Evidence and Person, or a leftover diary entry blocks the delete. Person is last
# because seized_items.seized_from, evidence.linked_person_id and statements.person_id all
# reference it.
_CASE_CHILDREN = (CaseDiaryEntry, AuditLog, LegalSection, Judgment, Document,
                  Evidence, Statement, SeizedItem, Person)


def _reset_case(db, spec: dict, owner: User) -> Case | None:
    """Wipe every child row of an already-seeded demo case and rebuild it to the EXACT seed
    baseline, preserving the case row's id (the DEMO_MODE cache is keyed by case_id, so a
    fresh id would break every cached lookup). Returns the case, or None if it was never
    seeded (nothing to reset)."""
    case_number = spec["case"]["case_number"]
    case = db.query(Case).filter(Case.case_number == case_number).first()
    if case is None:
        return None
    cid = case.id

    # document_versions first (FK -> documents), then the case_id-keyed children.
    doc_ids = [row[0] for row in db.query(Document.id).filter(Document.case_id == cid).all()]
    if doc_ids:
        db.query(DocumentVersion).filter(
            DocumentVersion.document_id.in_(doc_ids)
        ).delete(synchronize_session=False)
    for model in _CASE_CHILDREN:
        db.query(model).filter(model.case_id == cid).delete(synchronize_session=False)
    db.flush()

    # Restore any case fields a demo run may have PATCHed (e.g. status), then rebuild the
    # pool + diary. created_by is left untouched so ownership (the RBAC demo) is preserved.
    for field, value in spec["case"].items():
        setattr(case, field, value)
    _populate_children(db, case, spec, owner)
    return case


def seed() -> None:
    db = SessionLocal()
    try:
        # --- Users (idempotent per-username) ---
        user_status = []
        users: dict[str, User] = {}
        for data in DEMO_USERS:
            user, created = _get_or_create_user(db, data)
            users[data["username"]] = user
            user_status.append(f"{user.username} ({user.role.value}): "
                               f"{'created' if created else 'exists'}")

        # --- Cases (idempotent per-case_number) ---
        case_status = []
        for spec in DEMO_CASES:
            case, created = _seed_case(db, spec, users[spec["owner"]])
            if created:
                case_status.append(
                    f"{case.case_number} (id={case.id}, owner={spec['owner']}): created "
                    f"- {len(spec['persons'])} person(s), "
                    f"{len(spec['seized_items'])} seized item(s), "
                    f"{len(spec['statements'])} statement(s), "
                    f"{len(spec.get('diary', []))} diary entry(ies)"
                )
            else:
                case_status.append(
                    f"{case.case_number} (id={case.id}): exists - skipped"
                )

        db.commit()
        print("Users:")
        for s in user_status:
            print("  -", s)
        print("Cases:")
        for s in case_status:
            print("  -", s)
    finally:
        db.close()


def reset() -> None:
    """Reset the two demo cases to their exact seed baseline: every child row (legal
    sections, judgments, documents + versions, evidence, statements, seized items, diary,
    audit) is wiped and the pool + seeded diary are rebuilt. Case rows and users are kept
    (ids preserved). Use before a demo when test runs have accumulated diary/section/doc
    rows.  Run:  python -m app.seed --reset"""
    db = SessionLocal()
    try:
        # Owners must exist to rebuild the children; reuse the idempotent user seeding.
        users: dict[str, User] = {}
        for data in DEMO_USERS:
            user, _ = _get_or_create_user(db, data)
            users[data["username"]] = user

        summary = []
        for spec in DEMO_CASES:
            case = _reset_case(db, spec, users[spec["owner"]])
            if case is None:
                summary.append(
                    f"{spec['case']['case_number']}: NOT FOUND — run `python -m app.seed` first"
                )
                continue
            db.flush()
            diary_n = (
                db.query(CaseDiaryEntry).filter(CaseDiaryEntry.case_id == case.id).count()
            )
            sect_n = db.query(LegalSection).filter(LegalSection.case_id == case.id).count()
            doc_n = db.query(Document).filter(Document.case_id == case.id).count()
            summary.append(
                f"{case.case_number} (id={case.id}): reset — {diary_n} diary entry(ies), "
                f"{sect_n} legal section(s), {doc_n} document(s)"
            )

        db.commit()
        print("Reset demo cases to seed baseline:")
        for s in summary:
            print("  -", s)
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Seed or reset the CrimeGPT demo database.")
    ap.add_argument(
        "--reset",
        action="store_true",
        help="wipe the two demo cases' child rows and rebuild them to the seed baseline "
        "(preserves case ids and users)",
    )
    args = ap.parse_args()
    if args.reset:
        reset()
    else:
        seed()
