from pathlib import Path

import yaml

from jobhunter.scoring import Scorer

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "keywords.yaml").read_text(encoding="utf-8"))


def test_relevant_job_scores_high_and_lists_reasons():
    score, reason, relevant = Scorer(CFG).score("AI Automation Specialist (n8n / Zapier)", "Build AI agents in Python.")
    assert relevant and score >= 70
    assert "n8n" in reason and "zapier" in reason


def test_penalties_reduce_score():
    s = Scorer(CFG)
    base, _, _ = s.score("Automation Specialist", "Use Zapier.")
    pen, reason, _ = s.score("Senior Automation Specialist", "Use Zapier. 7+ years experience. US citizen.")
    assert pen < base and "−" in reason


def test_irrelevant_job_is_not_relevant():
    assert Scorer(CFG).score("Registered Nurse", "Patient care in clinics.")[2] is False


def test_score_is_clamped():
    score, _, _ = Scorer(CFG).score("AI automation n8n Zapier AI agent chatbot Arabic video editor", "")
    assert score == 100
