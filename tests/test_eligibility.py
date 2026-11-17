import pytest

from jobhunter.eligibility import CHECK, ELIGIBLE, RESTRICTED, classify


@pytest.mark.parametrize("location", [
    "Worldwide", "Anywhere in the World", "Anywhere", "Global", "MENA", "Middle East",
    "Iraq", "EMEA", "Europe, Middle East", "Remote - Worldwide",
])
def test_open_locations_are_eligible(location):
    assert classify(location, "AI Automation Specialist", "")[0] == ELIGIBLE


@pytest.mark.parametrize("location", [
    "USA Only", "USA", "US", "Europe Only", "EU", "Egypt", "Canada Only", "United Kingdom",
    "USA, Canada, USA timezones", "LATAM, Europe, USA, Canada, APAC", "Menlo Park",
    "Europe, USA, Canada, Australia, Singapore, Mexico, Saudi Arabia", "Anywhere in the US",
    "Your Remote US Home Office",
])
def test_country_restricted_locations_are_dropped(location):
    assert classify(location, "AI Automation Specialist", "")[0] == RESTRICTED


@pytest.mark.parametrize("location", ["", "Remote", "remote", "Fully Remote", None])
def test_unclear_location_is_kept_for_checking(location):
    assert classify(location, "n8n Developer", "Build workflows.")[0] == CHECK


def test_unclear_location_with_worldwide_in_description_is_eligible():
    assert classify("Remote", "n8n Developer", "We hire from anywhere.")[0] == ELIGIBLE


def test_himalayas_empty_list_means_worldwide():
    assert classify([], "AI Agent Builder", "")[0] == ELIGIBLE


def test_himalayas_list_including_iraq_is_eligible():
    assert classify(["Jordan", "Iraq", "Egypt"], "AI Agent Builder", "")[0] == ELIGIBLE


def test_himalayas_list_without_iraq_is_restricted():
    assert classify(["Egypt"], "Arabic Content Producer", "")[0] == RESTRICTED
    assert classify(["United States", "Canada"], "Zapier Expert", "")[0] == RESTRICTED


@pytest.mark.parametrize("title", [
    "Web Developer: WordPress (U.S. Based, Remote Contractor)",
    "Video Editor - US Only",
    "Automation Engineer (EU-based)",
    "Arabic Content Producer — Egypt only",
])
def test_restriction_in_title_wins_over_worldwide(title):
    assert classify("Worldwide", title, "")[0] == RESTRICTED
    assert classify([], title, "")[0] == RESTRICTED


@pytest.mark.parametrize("desc", [
    "You must reside in the United States to be considered.",
    "Candidates must be authorized to work in the US.",
    "This role is only open to candidates based in Canada.",
    "US citizenship required due to government contracts.",
])
def test_restriction_in_description_drops_job(desc):
    assert classify("Worldwide", "Python Automation Engineer", desc)[0] == RESTRICTED


@pytest.mark.parametrize("title", [
    "Sales Development Representative, Singapore",
    "Software Development Engineer II (Remote @ Colombia)",
    "Senior Software Engineer LATAM",
    "Conversational Designer, APAC",
])
def test_place_in_title_overrides_anywhere(title):
    assert classify("Anywhere in the World", title, "")[0] == RESTRICTED


def test_global_in_title_is_fine():
    assert classify([], "AI Product Manager - Agentic Platform (Global)", "")[0] == ELIGIBLE


def test_pronoun_us_is_not_a_restriction():
    assert classify("Worldwide", "Chatbot Builder", "Contact us only through the form. Join us based on merit.")[0] == ELIGIBLE


def test_only_open_to_mena_is_not_restricted():
    status, _ = classify("Remote", "Arabic Chatbot Trainer", "This role is only open to candidates in the MENA region.")
    assert status == ELIGIBLE
