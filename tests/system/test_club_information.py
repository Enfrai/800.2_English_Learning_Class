"""Verify separate public pages, readable class details and standalone login.

Author: Sandhya Tiwari
Date: 26 Oct 2026
Updated: Shuohui Liu, 26 Oct 2026
"""

import re

from playwright.sync_api import expect


def test_class_information_is_public_without_a_session(page):
    """
    Verify that class information is public without a session.
    """
    response = page.goto("/class-information")
    assert response.status == 200
    expect(page.get_by_role("heading", name="English classes", exact=True)).to_be_visible()
    facts = page.locator("#class-information")
    for label in ("Class day", "Class time", "Venue address", "Contact"):
        expect(facts.get_by_text(label, exact=True)).to_be_visible()
    expect(facts.get_by_role("link")).to_have_count(1)
    expect(page.get_by_role("link", name="Learners", exact=True)).to_have_count(0)
    expect(page.get_by_role("link", name="Staff login", exact=True)).to_be_visible()


def test_public_page_fits_a_phone_and_keeps_body_text_readable(page):
    """
    Verify that public page fits a phone and keeps body text readable.
    """
    page.set_viewport_size({"width": 360, "height": 800})
    page.goto("/class-information")
    expect(page.get_by_label("Username", exact=True)).to_have_count(0)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator("#class-information dd").evaluate_all(
        "items => items.every(item => parseFloat(getComputedStyle(item).fontSize) >= 18)"
    )


def test_public_copy_uses_short_sentences_without_learner_photos(page):
    """
    Verify that public copy uses short sentences without learner photos.
    """
    page.goto("/class-information")
    expect(page.get_by_label("Name (required)", exact=True)).to_have_count(0)
    expect(page.get_by_label("Username", exact=True)).to_have_count(0)
    for text in page.locator("h1,h2,h3,p,dt,dd,label,legend,button").all_text_contents():
        for sentence in re.split(r"[.!?]+(?:\s|$)", text):
            assert len(sentence.split()) <= 15, sentence
    expect(page.locator("img,video")).to_have_count(0)


def test_unknown_public_address_has_http_404_and_home_link(page):
    """
    Verify that unknown public address has http 404 and home link.
    """
    response = page.goto("/missing-public-information")
    assert response.status == 404
    expect(page.get_by_role("heading", name="Page not found", exact=True)).to_be_visible()
    page.get_by_role("link", name="Go to home page", exact=True).click()
    expect(page.get_by_label("Username", exact=True)).to_be_visible()


def test_public_navigation_opens_separate_contents(page):
    """
    Verify that public navigation opens separate contents.
    """
    page.goto("/")
    expect(page.get_by_label("Username", exact=True)).to_be_visible()
    nav = page.get_by_role("navigation", name="Public menu")
    nav.get_by_role("link", name="Class information", exact=True).click()
    expect(page.locator("#class-information")).to_be_visible()
    expect(page.get_by_label("Username", exact=True)).to_have_count(0)
    nav.get_by_role("link", name="Ask about classes", exact=True).click()
    expect(page.get_by_label("Name (required)", exact=True)).to_be_visible()
    expect(page.locator("#class-information")).to_have_count(0)
    nav.get_by_role("link", name="Staff login", exact=True).click()
    expect(page.get_by_label("Username", exact=True)).to_be_visible()
    expect(page.get_by_label("Name (required)", exact=True)).to_have_count(0)
