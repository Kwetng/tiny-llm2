"""PII and sensitive-data redaction, applied before text leaves the platform boundary or reaches a log."""
import re

PATTERNS = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("SORT_CODE", re.compile(r"\b\d{2}-\d{2}-\d{2}\b")),
    ("ACCOUNT_NO", re.compile(r"(?i)\b(?:account(?: number| no\.?)?|acct)\s*[:#]?\s*(\d{8})\b")),
    ("NI_NUMBER", re.compile(r"\b(?!BG|GB|NK|KN|TN|NT|ZZ)[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b")),
    ("UK_PHONE", re.compile(r"(?<!\d)(?:\+44\s?7\d{3}|07\d{3})\s?\d{3}\s?\d{3}(?!\d)")),
]


def _luhn(digits: str) -> bool:
    d = [int(c) for c in digits][::-1]
    return sum(x if i % 2 == 0 else (x * 2 - 9 if x * 2 > 9 else x * 2) for i, x in enumerate(d)) % 10 == 0


def redact(text: str):
    """Return (redacted_text, findings). Findings list the TYPES found, never the values."""
    findings = []
    out = text
    for kind, pat in PATTERNS:
        def sub(m, kind=kind):
            val = m.group(0)
            if kind == "CARD":
                digits = re.sub(r"\D", "", val)
                if not (13 <= len(digits) <= 19 and _luhn(digits)):
                    return val                       # not a real card number (e.g. a deal amount)
            if kind == "ACCOUNT_NO":
                findings.append(kind)
                return val.replace(m.group(1), "[ACCOUNT_NO]")
            findings.append(kind)
            return f"[{kind}]"
        out = pat.sub(sub, out)
    return out, findings


def contains_pii(text: str) -> bool:
    return bool(redact(text)[1])
