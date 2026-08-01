"""Python Enums for every enum column in the schema (CLAUDE.md Section 5).

All members use value == name so the stored string matches the schema label
(e.g. UserRole.IO -> "IO").
"""
import enum


class UserRole(str, enum.Enum):
    IO = "IO"
    SHO = "SHO"
    LEGAL_ADVISOR = "LEGAL_ADVISOR"


class CaseType(str, enum.Enum):
    CONVENTIONAL = "CONVENTIONAL"
    CYBER_FINANCIAL = "CYBER_FINANCIAL"


class CaseStatus(str, enum.Enum):
    COMPLAINT = "COMPLAINT"
    INVESTIGATION = "INVESTIGATION"
    ARREST = "ARREST"
    REMAND = "REMAND"
    CHARGESHEET = "CHARGESHEET"


class Language(str, enum.Enum):
    GU = "GU"
    HI = "HI"
    EN = "EN"


class PersonRole(str, enum.Enum):
    VICTIM = "VICTIM"
    ACCUSED = "ACCUSED"
    WITNESS = "WITNESS"
    COMPLAINANT = "COMPLAINANT"


# Form I item xix (Gujarat Police Report to Magistrate Rules 2025) — status of accused.
# Uppercase name==value matches PersonRole / CaseStatus convention.
class AccusedStatus(str, enum.Enum):
    FORWARDED = "FORWARDED"
    BAILED_BY_POLICE = "BAILED_BY_POLICE"
    BAILED_BY_COURT = "BAILED_BY_COURT"
    JUDICIAL_CUSTODY = "JUDICIAL_CUSTODY"
    ABSCONDING = "ABSCONDING"
    PROCLAIMED_OFFENDER = "PROCLAIMED_OFFENDER"


class EvidenceType(str, enum.Enum):
    IMAGE = "IMAGE"
    DOCUMENT = "DOCUMENT"
    PHYSICAL = "PHYSICAL"


class StatementType(str, enum.Enum):
    WITNESS = "WITNESS"
    ACCUSED = "ACCUSED"
    VICTIM = "VICTIM"


class LegalAct(str, enum.Enum):
    BNS = "BNS"
    BNSS = "BNSS"
    BSA = "BSA"
    IT_ACT = "IT_ACT"
    OTHER = "OTHER"


class SectionStatus(str, enum.Enum):
    SUGGESTED = "SUGGESTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class DocType(str, enum.Enum):
    PANCHNAMA = "PANCHNAMA"
    REMAND = "REMAND"
    SEIZURE_RECEIPT = "SEIZURE_RECEIPT"
    MEDICAL_LETTER = "MEDICAL_LETTER"
    CUSTODY_LETTER = "CUSTODY_LETTER"
    FACE_ID = "FACE_ID"
    CHARGESHEET = "CHARGESHEET"
    LERS_REQUEST = "LERS_REQUEST"
    LERS_PRESERVATION_REQUEST = "LERS_PRESERVATION_REQUEST"
    LERS_RECORDS_REQUEST = "LERS_RECORDS_REQUEST"


class DocStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"


class ActivityType(str, enum.Enum):
    COMPLAINT = "COMPLAINT"
    WITNESS_EXAM = "WITNESS_EXAM"
    EVIDENCE_SEIZURE = "EVIDENCE_SEIZURE"
    ARREST = "ARREST"
    REMAND = "REMAND"
    DOC_GENERATED = "DOC_GENERATED"
    OTHER = "OTHER"


class AuditAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
