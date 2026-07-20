"""Seed demo users and the demo cases (CLAUDE.md §15). Safe to re-run (idempotent).

Run from backend/:  python -m app.seed

Deterministic by design: every value below is a literal — no now(), no random, no
faker. A fresh database + `alembic upgrade head` + `python -m app.seed` always
produces byte-identical demo content, so the demo starts from a known state.

The seed populates the *pool only* (users, cases, persons, seized items,
statements). It deliberately creates NO legal_sections, documents, diary entries
or audit rows: those are produced live by the demo flow itself (§15 steps 4-6),
which is the whole point of showing them being generated on stage.

Two cases, owned by two different IOs so the RBAC visibility rule (§9) is
demonstrable on the case list:
  I-CR-0142-2026  house theft   - owner `io`  - full pool, the demo centrepiece
  I-CR-0199-2026  vehicle theft - owner `io2` - lighter pool, status COMPLAINT
Logged in as `io` you see one case; as `sho` you see both.
"""
from datetime import date, datetime

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Case, Person, SeizedItem, Statement, User
from app.models.enums import (
    CaseStatus,
    CaseType,
    Language,
    PersonRole,
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
    },
    {
        "username": "io2",
        "password": "io2123",
        "full_name": "Sub-Inspector Meera Joshi",
        "role": UserRole.IO,
        "rank": "Police Sub-Inspector",
        "badge_no": "GJ-AMD-5518",
    },
    {
        "username": "sho",
        "password": "sho123",
        "full_name": "SHO Bhavna Desai",
        "role": UserRole.SHO,
        "rank": "Police Inspector (SHO)",
        "badge_no": "GJ-AMD-2210",
    },
    {
        "username": "legal",
        "password": "legal123",
        "full_name": "Adv. Nikhil Mehta",
        "role": UserRole.LEGAL_ADVISOR,
        "rank": "Legal Advisor",
        "badge_no": "GJ-BAR-1187",
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
CREATED_AT_HOUSE_THEFT = datetime(2026, 7, 10, 9, 15)
CREATED_AT_VEHICLE_THEFT = datetime(2026, 7, 15, 18, 40)

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
    },
]

# The demo centrepiece — used as the default by demo_cache_build and preflight.
DEMO_CASE_NUMBER = DEMO_CASES[0]["case"]["case_number"]


def _get_or_create_user(db, data) -> tuple[User, bool]:
    user = db.query(User).filter(User.username == data["username"]).first()
    if user is not None:
        # Backfill rank/badge_no on already-seeded users (existing data survives).
        user.rank = data["rank"]
        user.badge_no = data["badge_no"]
        return user, False
    user = User(
        username=data["username"],
        password_hash=hash_password(data["password"]),
        full_name=data["full_name"],
        role=data["role"],
        rank=data["rank"],
        badge_no=data["badge_no"],
    )
    db.add(user)
    db.flush()
    return user, True


def _seed_case(db, spec: dict, owner: User) -> tuple[Case, bool]:
    """Create one case and its pool. Idempotent per case_number."""
    case_number = spec["case"]["case_number"]
    existing = db.query(Case).filter(Case.case_number == case_number).first()
    if existing is not None:
        return existing, False

    case = Case(**spec["case"], created_by=owner.id)
    db.add(case)
    db.flush()

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

    return case, True


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
                    f"{len(spec['statements'])} statement(s)"
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


if __name__ == "__main__":
    seed()
