"""Credit Support Annex (CSA) term extraction.

Turns contract text into a fixed schema. Every field carries:
  value       - the parsed value (amounts as {currency, amount})
  confidence  - how sure the extractor is (standard ISDA wording scores high, loose wording low)
  source      - document, line number and the exact line the value came from (lineage for audit)

Amendments are applied on top of the base CSA with their effective date, and the lineage
shows both documents. Any critical field below the confidence bar, or missing, sends the whole
record to the human review queue; nothing goes to the collateral system unreviewed.

The rules below are deliberately transparent. In production the same schema and routing wrap
Azure AI Document Intelligence / Google Document AI plus a multimodal LLM for layout and OCR.
"""
import re
from pathlib import Path

from .config import DATA

CRITICAL = ("base_currency", "threshold_party_a", "threshold_party_b", "minimum_transfer_amount", "agreement_date")
REVIEW_BELOW = 0.80
AMT = r"(zero|nil|(?:GBP|USD|EUR)\s*[\d,.]+(?:\s*(?:million|thousand))?)"


def parse_amount(s):
    s = s.strip().rstrip(".;")
    if s.lower() in ("zero", "nil"):
        return {"currency": None, "amount": 0.0}
    m = re.match(r"(GBP|USD|EUR)\s*([\d,.]+)\s*(million|thousand)?", s)
    if not m:
        return None
    mult = {"million": 1e6, "thousand": 1e3}.get(m.group(3), 1)
    return {"currency": m.group(1), "amount": float(m.group(2).replace(",", "")) * mult}


def _find(lines, rules):
    """rules: list of (regex, confidence, group, transform). First match wins, in rule order."""
    for pat, conf, grp, fn in rules:
        for n, line in enumerate(lines, 1):
            m = re.search(pat, line)
            if m:
                return {"value": fn(m.group(grp)), "confidence": conf, "line": n, "text": line.strip()}
    return {"value": None, "confidence": 0.0, "line": None, "text": None}


def extract_document(path: Path):
    text = path.read_text()
    lines = text.splitlines()
    ref = _find(lines, [(r"Reference:\s*(\S+)", 0.99, 1, str)])["value"]
    amending = _find(lines, [(r"Amending:\s*(\S+)", 0.99, 1, str)])["value"]
    ident = lambda x: x.strip()
    if amending:
        eff = _find(lines, [(r"with effect from (\d{1,2} \w+ \d{4})", 0.95, 1, ident)])
        fields = {
            "threshold_party_b": _find(lines, [(r"Threshold with respect to Party B is amended to " + AMT, 0.95, 1, parse_amount)]),
            "threshold_party_a": _find(lines, [(r"Threshold with respect to Party A is amended to " + AMT, 0.95, 1, parse_amount)]),
            "minimum_transfer_amount": _find(lines, [(r"Minimum Transfer Amount with respect to each party is amended to " + AMT, 0.95, 1, parse_amount)]),
        }
        return {"reference": ref, "amends": amending, "effective": eff["value"],
                "fields": {k: v for k, v in fields.items() if v["value"] is not None}, "doc": path.name}

    collateral = []
    for n, line in enumerate(lines, 1):
        m = re.search(r"\(([A-Z])\)\s+(.+?):\s*(\d+(?:\.\d+)?)%", line)
        if m:
            collateral.append({"asset": m.group(2).strip(), "valuation_percentage": float(m.group(3)), "line": n})
    fields = {
        "counterparty": _find(lines, [(r'and ([A-Z][A-Z &.]+?) \("Party B"\)', 0.95, 1, ident)]),
        "agreement_date": _find(lines, [(r"dated as of (\d{1,2} \w+ \d{4})", 0.95, 1, ident)]),
        "base_currency": _find(lines, [(r'"Base Currency" means (GBP|USD|EUR)', 0.97, 1, ident),
                                       (r"base currency (?:for this Annex )?shall be (GBP|USD|EUR)", 0.75, 1, ident)]),
        "threshold_party_a": _find(lines, [(r'"Threshold" means,? with respect to Party A:\s*' + AMT, 0.95, 1, parse_amount),
                                           (r"Party A's threshold is " + AMT, 0.7, 1, parse_amount)]),
        "threshold_party_b": _find(lines, [(r"with respect to Party B:\s*" + AMT, 0.95, 1, parse_amount),
                                           (r"Threshold applicable to Party B shall be " + AMT, 0.72, 1, parse_amount)]),
        "minimum_transfer_amount": _find(lines, [(r'"Minimum Transfer Amount" means, with respect to each party, ' + AMT, 0.95, 1, parse_amount),
                                                 (r"Transfers below " + AMT + r" will not be required", 0.65, 1, parse_amount)]),
        "independent_amount": _find(lines, [(r'"Independent Amount" means, with respect to (?:each party|Party [AB]), ([^.]+)', 0.9, 1, ident)]),
        "valuation_agent": _find(lines, [(r'"Valuation Agent" means (Party A|Party B)', 0.95, 1, ident),
                                         (r"Valuation Agent:\s*(.+?)\.?$", 0.6, 1, ident)]),
        "notification_time": _find(lines, [(r'"Notification Time" means ([^,]+), London time', 0.95, 1, ident)]),
        "governing_law": _find(lines, [(r"governed by (English|New York) law", 0.95, 1, ident),
                                       (r"laws of (?:the State of )?(New York|England)", 0.8, 1, lambda x: "English" if x == "England" else x)]),
        "eligible_collateral": {"value": [{k: v for k, v in c.items() if k != "line"} for c in collateral] or None,
                                "confidence": 0.9 if collateral else 0.0, "line": collateral[0]["line"] if collateral else None,
                                "text": f"{len(collateral)} eligible collateral lines" if collateral else None},
    }
    return {"reference": ref, "amends": None, "fields": fields, "doc": path.name}


def extract_all(folder=DATA / "contracts"):
    docs = [extract_document(p) for p in sorted(folder.glob("*.txt"))]
    base = {d["reference"]: d for d in docs if not d["amends"]}
    records = {}
    for ref, d in base.items():
        fields = {k: {**v, "source": {"doc": d["doc"], "line": v["line"], "text": v["text"]}} for k, v in d["fields"].items()}
        applied = []
        for a in (x for x in docs if x["amends"] == ref):
            for k, v in a["fields"].items():
                fields[k] = {**v, "source": {"doc": a["doc"], "line": v["line"], "text": v["text"]},
                             "supersedes": fields[k]["value"], "effective": a["effective"]}
            applied.append({"reference": a["reference"], "effective": a["effective"], "fields": sorted(a["fields"])})
        reasons = []
        for k in CRITICAL:
            f = fields[k]
            if f["value"] is None:
                reasons.append(f"{k}: missing")
            elif f["confidence"] < REVIEW_BELOW:
                reasons.append(f"{k}: confidence {f['confidence']:.2f}")
        for f in fields.values():
            f.pop("line", None); f.pop("text", None)
        records[ref] = {"reference": ref, "fields": fields, "amendments_applied": applied,
                        "status": "NEEDS HUMAN REVIEW" if reasons else "AUTO-APPROVED FOR COLLATERAL SYSTEM", "review_reasons": reasons}
    return records
