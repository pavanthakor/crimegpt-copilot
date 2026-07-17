"""Seed demo users and one CONVENTIONAL demo case. Safe to re-run (idempotent).

Run from backend/:  python -m app.seed
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
    },
    {
        "username": "sho",
        "password": "sho123",
        "full_name": "SHO Bhavna Desai",
        "role": UserRole.SHO,
    },
    {
        "username": "legal",
        "password": "legal123",
        "full_name": "Adv. Nikhil Mehta",
        "role": UserRole.LEGAL_ADVISOR,
    },
]

DEMO_CASE_NUMBER = "I-CR-0142-2026"

# Bilingual complaint narrative (Gujarati primary + English translation).
COMPLAINT_NARRATIVE = (
    "ગુજરાતી: તારીખ ૧૦/૦૭/૨૦૨૬ ના રોજ રાત્રે આશરે ૦૨:૩૦ કલાકે, હું અને મારો પરિવાર "
    "ઊંઘમાં હતા ત્યારે કોઈ અજાણ્યા ઈસમે મારા ઘરની પાછળની બારીનો લોખંડનો કઠેડો તોડી "
    "ઘરમાં પ્રવેશ કર્યો હતો. તેણે કબાટમાંથી સોનાનો ચેન તથા રોકડ રૂ. ૨૫,૦૦૦ ચોરી "
    "કરી નાસી ગયો હતો. પાડોશી તથા સોસાયટીના ચોકીદારે શંકાસ્પદ ઈસમને ભાગતો જોયો હતો.\n\n"
    "English: On 10/07/2026 at about 02:30 hrs, while my family and I were asleep, "
    "an unknown person broke the iron grille of the rear window of my house and "
    "entered. He stole a gold chain and cash of Rs. 25,000 from the cupboard and "
    "fled. My neighbour and the society watchman saw the suspect running away."
)


def _get_or_create_user(db, data) -> tuple[User, bool]:
    user = db.query(User).filter(User.username == data["username"]).first()
    if user is not None:
        return user, False
    user = User(
        username=data["username"],
        password_hash=hash_password(data["password"]),
        full_name=data["full_name"],
        role=data["role"],
    )
    db.add(user)
    db.flush()
    return user, True


def seed() -> None:
    db = SessionLocal()
    try:
        # --- Users (idempotent per-username) ---
        user_status = []
        for data in DEMO_USERS:
            user, created = _get_or_create_user(db, data)
            user_status.append(f"{user.username} ({user.role.value}): "
                               f"{'created' if created else 'exists'}")
        io_user = db.query(User).filter(User.username == "io").first()

        # --- Demo case (skip whole block if already seeded) ---
        existing = db.query(Case).filter(
            Case.case_number == DEMO_CASE_NUMBER
        ).first()
        if existing is not None:
            db.commit()
            print("Users:")
            for s in user_status:
                print("  -", s)
            print(f"Case {DEMO_CASE_NUMBER} already exists "
                  f"(id={existing.id}) - case seed skipped.")
            return

        case = Case(
            case_number=DEMO_CASE_NUMBER,
            case_type=CaseType.CONVENTIONAL,
            title="House theft of gold ornaments and cash - Satellite, Ahmedabad",
            fir_number="0142/2026",
            fir_date=date(2026, 7, 10),
            police_station="Satellite Police Station",
            district="Ahmedabad",
            status=CaseStatus.INVESTIGATION,
            incident_datetime=datetime(2026, 7, 10, 2, 30),
            incident_location="B/12 Shivalik Residency, Satellite, Ahmedabad",
            complaint_narrative=COMPLAINT_NARRATIVE,
            complaint_language=Language.GU,
            created_by=io_user.id,
        )
        db.add(case)
        db.flush()

        complainant = Person(
            case_id=case.id, role=PersonRole.COMPLAINANT,
            full_name="Rameshbhai Patel", father_name="Manubhai Patel",
            age=52, gender="M",
            address="B/12 Shivalik Residency, Satellite, Ahmedabad",
            phone="9825012345", occupation="Shopkeeper",
        )
        accused = Person(
            case_id=case.id, role=PersonRole.ACCUSED,
            full_name="Suresh Vaghela", alias="Suri",
            father_name="Kanubhai Vaghela", age=27, gender="M",
            address="Vasna labour quarters, Ahmedabad",
            phone="9700098765", occupation="Daily-wage labourer",
        )
        witness1 = Person(
            case_id=case.id, role=PersonRole.WITNESS,
            full_name="Kiran Shah", father_name="Dilipbhai Shah",
            age=45, gender="M",
            address="B/11 Shivalik Residency, Satellite, Ahmedabad",
            phone="9898011223", occupation="Neighbour / Businessman",
        )
        witness2 = Person(
            case_id=case.id, role=PersonRole.WITNESS,
            full_name="Prakash Rana", father_name="Govindbhai Rana",
            age=38, gender="M",
            address="Staff quarters, Shivalik Residency, Satellite",
            phone="9033044556", occupation="Society watchman",
        )
        db.add_all([complainant, accused, witness1, witness2])
        db.flush()

        item1 = SeizedItem(
            case_id=case.id,
            description="Gold chain, approx 18 grams, yellow metal",
            quantity=1, estimated_value=108000,
            seized_from=accused.id,
            seizure_datetime=datetime(2026, 7, 12, 11, 0),
            seizure_location="Vasna, Ahmedabad",
        )
        item2 = SeizedItem(
            case_id=case.id,
            description="Iron crowbar used to break the window grille",
            quantity=1, estimated_value=250,
            seized_from=accused.id,
            seizure_datetime=datetime(2026, 7, 12, 11, 0),
            seizure_location="Vasna, Ahmedabad",
        )
        db.add_all([item1, item2])

        statement = Statement(
            case_id=case.id, person_id=witness2.id,
            statement_type=StatementType.WITNESS,
            statement_text=(
                "On the night of 10/07/2026 at around 02:35 hrs I was on duty at "
                "the main gate of Shivalik Residency. I saw a man of medium build "
                "jump over the rear compound wall and run towards Vasna. I raised "
                "an alarm and informed the residents."
            ),
            language=Language.EN,
            recorded_by=io_user.id,
        )
        db.add(statement)

        db.commit()
        print("Users:")
        for s in user_status:
            print("  -", s)
        print(f"Created case {DEMO_CASE_NUMBER} (id={case.id}): "
              "1 complainant, 1 accused, 2 witnesses, 2 seized items, 1 statement.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
