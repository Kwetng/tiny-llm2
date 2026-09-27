"""Tests for the comparison harness. They need no API key and no model weights.

    pip install -r requirements.txt && pytest -q tests
"""
import json, os, subprocess, sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))
from borrowers import Portfolio, QUESTIONS            # noqa: E402
import decision_models as dm                          # noqa: E402


def laya_shaped_answers(p_true=0.9, score_probs=(0.6, 0.3, 0.1, 0, 0)):
    """Answers in the exact shape laya/agent.py builds (laya 0.3.20)."""
    keys = list(QUESTIONS["main_risk"]["criteria"])
    probs = [0.1, 0.05, 0.05, 0.1, 0.7]
    exp_score = float(sum(i * p for i, p in enumerate(score_probs)))
    return {
        "can_repay": {"type": "noul", "noul": p_true, "confidence": max(p_true, 1 - p_true)},
        "main_risk": {"type": "choice", "choice": keys[int(np.argmax(probs))],
                      "probabilities": dict(zip(keys, probs)), "confidence": 0.5},
        "risk_grade": {"type": "score", "score": exp_score,
                       "legend": {str(i): c for i, c in enumerate(QUESTIONS["risk_grade"]["criteria"])},
                       "probabilities": {str(i): p for i, p in enumerate(score_probs)}},
    }


class FakeAgent:
    def system_one(self, state, questions, **kw):
        assert isinstance(state, dict) and set(questions) == set(QUESTIONS)
        return {"answers": laya_shaped_answers(), "usage": {"input_tokens": 321}}


def test_laya_adapter_through_real_router():
    laya = pytest.importorskip("laya")
    router = laya.Router()
    router.load = lambda name: FakeAgent()               # only the checkpoint is faked; routing is real
    model = dm.LayaModel(router=router)
    out = model.ask(Portfolio(quick=True).state(900), QUESTIONS)
    assert out["p_repay"] == pytest.approx(0.9)
    assert out["main_risk"] == "none material" and out["main_risk_p"] == pytest.approx(0.7)
    assert out["grade"] == pytest.approx(1 + 0.5)         # Laya 0-based expected level 0.5 -> grade 1.5
    assert out["model_id"].endswith(":english")           # English JSON routes to the English checkpoint
    assert model.input_tokens == 321


def test_score_bases_are_normalised():
    a = dm._normalise({"can_repay": {"noul": .5}, "main_risk": {"choice": "x"}, "risk_grade": {"score": 0}}, 0, 1, "laya")
    b = dm._normalise({"can_repay": {"noul": .5}, "main_risk": {"choice": "x"}, "risk_grade": {"score": 1}}, 1, 1, "jev")
    assert a["grade"] == b["grade"] == 1


def test_same_borrowers_as_jev_credit_project():
    pf = Portfolio()
    assert len(pf.idx_test) == 400 and pf.idx_test[0] == 2600
    from sklearn.metrics import roc_auc_score
    assert roc_auc_score(pf.y[pf.idx_test], pf.pd_true[pf.idx_test]) == pytest.approx(0.731, abs=5e-4)


def test_jev_requires_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        dm.build("jev")


def test_dry_run_end_to_end(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "code" / "compare_credit.py"), "--dry-run", "--quick", "--out", str(tmp_path)],
                   check=True, capture_output=True)
    out = tmp_path / "plumbing_test"
    report = (out / "comparison_report.md").read_text()
    assert "PLUMBING TEST, NOT A MODEL COMPARISON" in report
    m = json.loads((out / "metrics.json").read_text())
    assert m["meta"]["plumbing_test"] is True
    for f in ("calibration.png", "roc.png", "pd_agreement.png", "latency.png", "decisions.jsonl"):
        assert (out / f).exists()
    # recalibration is monotone, so it must not change the ranking
    for name, r in m["models"].items():
        assert r["recalibrated"]["brier"] <= r["brier"] + 1e-9
