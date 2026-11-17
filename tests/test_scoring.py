from pathlib import Path

import pytest
import yaml

from jobhunter.eligibility import region_list_excluding_iraq
from jobhunter.scoring import Scorer, non_english, required_tools

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "keywords.yaml").read_text(encoding="utf-8"))
S = Scorer(CFG)

ENGLISH_FILLER = (
    "We are a small remote team and we are looking for someone who can work with our clients. "
    "You will be part of the team and you will help us build the future of our product. "
)


def score(title, desc=""):
    return S.score(title, desc)


# ---------------------------------------------------------------- normalisation / caps

def test_strong_multi_group_match_reaches_80():
    s, reason, relevant = score(
        "AI Automation Specialist (n8n / Zapier)",
        ENGLISH_FILLER + "Build AI agents and chatbots with OpenAI and Python. Junior friendly.",
    )
    assert relevant and s >= 80, reason


def test_single_mention_stays_low():
    s, _, relevant = score("Data Analyst", ENGLISH_FILLER + "Some Python scripting.")
    assert relevant and s < 30


def test_scores_do_not_saturate():
    """The old scorer gave many jobs 100. A strong but one-area job must stay clearly below
    a job that is strong in several areas."""
    one_area, _, _ = score("Video Editor", ENGLISH_FILLER + "Video editing, CapCut, DaVinci Resolve, motion graphics, "
                                         "short-form video, content creator.")
    many, _, _ = score("AI Video Editor — Arabic", ENGLISH_FILLER + "AI video with HeyGen and Runway, n8n automation, "
                                                  "Arabic content producer.")
    assert one_area < 90 and many > one_area


def test_group_cap_limits_single_area():
    # dozens of video keywords: video group must stop at its cap
    _, reason, _ = score("Video Editor", "video editing ai video content producer content creator capcut motion graphics "
                                         "short-form video premiere pro after effects davinci resolve")
    assert "video 60↑" in reason


def test_score_bounds():
    for t in ["", "Nurse", "AI automation n8n Zapier AI agent chatbot Arabic video editor"]:
        assert 0 <= score(t)[0] <= 100


def test_irrelevant_job_is_not_relevant():
    assert score("Registered Nurse", "Patient care in clinics.")[2] is False


# ---------------------------------------------------------------- penalties

BASE_T = "AI Automation Specialist"
BASE_D = ENGLISH_FILLER + "Build n8n and Zapier workflows."


@pytest.mark.parametrize("title,extra", [
    ("Senior AI Automation Specialist", ""),
    ("AI Automation Lead", ""),
    (BASE_T, "You have 5+ years of experience."),
    (BASE_T, "You have 4+ years of experience."),
    (BASE_T, "Requires 6-8 years in automation."),
    (BASE_T, "English at C1 level or higher."),
    (BASE_T, "Native English speaker required."),
    (BASE_T, "We hire candidates in the US, UK, Germany and Poland."),
])
def test_penalty_lowers_score(title, extra):
    base, _, _ = score(BASE_T, BASE_D)
    pen, reason, _ = score(title, BASE_D + " " + extra)
    assert pen < base, reason
    assert "−" in reason


def test_year_range_uses_minimum():
    _, reason, _ = score(BASE_T, BASE_D + " 2 to 6 years of professional experience. Also 1-5 years is fine.")
    assert "years" not in reason
    _, reason, _ = score(BASE_T, BASE_D + " 5-7 years of experience.")
    assert "5+ years" in reason


def test_arabic_c1_is_not_penalised():
    _, reason, _ = score("Arabic Language Specialist", BASE_D + " Verified Arabic language proficiency of C1 or C2.")
    assert "C1" not in reason
    _, reason, _ = score("Arabic Language Specialist", BASE_D + " Fluent written and spoken English (C1 or above).")
    assert "English C1/C2" in reason


def test_lead_generation_is_not_seniority():
    _, reason, _ = score("Lead Generation & Zapier Automation Specialist", BASE_D)
    assert "seniority" not in reason


def test_premiere_required_is_penalised_but_nice_to_have_is_not():
    t = "Video Editor"
    req = ENGLISH_FILLER + "\nRequirements\n• Premiere Pro and After Effects\n• Good taste\n"
    opt = ENGLISH_FILLER + "\nNice to have\n• Premiere Pro and After Effects\n"
    inline = ENGLISH_FILLER + "\nMust be proficient in Premiere Pro.\n"
    s_req, r_req, _ = score(t, req)
    s_opt, r_opt, _ = score(t, opt)
    s_inl, r_inl, _ = score(t, inline)
    assert "Premiere Pro required" in r_req and "After Effects required" in r_req
    assert "required" not in r_opt
    assert "Premiere Pro required" in r_inl
    assert s_req < s_opt


def test_penalty_group_is_capped():
    _, reason, _ = score("Senior Staff Lead Director AI Automation", BASE_D + " 10+ years. 5+ years.")
    assert "seniority -35" in reason


def test_non_english_posting_penalised():
    german = ("Wir suchen eine engagierte Person für unser Team. Du baust Automatisierungen mit n8n und Zapier, "
              "arbeitest eng mit unserem Vertrieb zusammen und bist verantwortlich für die Weiterentwicklung "
              "unserer Prozesse. Wir bieten flexible Arbeitszeiten, ein junges Team und viel Freiraum.")
    s_de, reason, _ = score("AI Automation Specialist", german)
    s_en, _, _ = score(BASE_T, BASE_D)
    assert "non-English" in reason and s_de < s_en


# ---------------------------------------------------------------- detectors directly

def test_non_english_detector():
    assert non_english(ENGLISH_FILLER * 2) is False
    assert non_english("Buscamos un editor de vídeo con experiencia en redes sociales para nuestra agencia "
                       "creativa. Trabajarás con clientes de todo el mundo y tendrás libertad creativa "
                       "para proponer ideas nuevas cada semana en nuestro equipo.") is True


def test_arabic_posting_is_not_non_english():
    arabic = ("نبحث عن صانع محتوى باللغة العربية للعمل عن بعد. ستقوم بكتابة وإنتاج فيديوهات قصيرة "
              "لمنصات التواصل الاجتماعي، والتعاون مع فريق التسويق لتطوير أفكار جديدة كل أسبوع.")
    assert non_english(arabic) is False


def test_region_list_detector():
    assert region_list_excluding_iraq("We hire candidates in the US, UK, Germany and Poland.")
    assert region_list_excluding_iraq("Open to candidates in Europe and LATAM time zones.")
    assert region_list_excluding_iraq("We hire in the US, UK, and the MENA region.") is None
    assert region_list_excluding_iraq("Our offices are in London and New York.") is None   # no hiring context


def test_required_tools_detector_ignores_responsibilities():
    import re
    pats = [("Premiere Pro", re.compile("premiere pro", re.I))]
    text = "Responsibilities\n• Edit videos in Premiere Pro\nRequirements\n• A good portfolio\n"
    assert required_tools(text, pats) == []
