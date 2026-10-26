# US-009: public club information

Open `/class-information` without signing in for class day, time, venue and
contact. The root `/` keeps the original standalone staff login. The enquiry
form has its own `/ask-about-classes` page. The public menu navigates between
these URLs and marks the current page. No page combines the three contents.
Teacher and coordinator home pages and login destinations remain unchanged.

The page uses the shared Ako tokens and controls. It renders class information
on the server without calling an authenticated API. No database migration is
required. Online content editing is outside this story.

## Content approval

Edit `web/src/content/club.json`, then rebuild the web image.
The checked-in day, time and address are examples, clearly labelled on screen.
Replace all four schedule fields with details confirmed by Julie and set
`schedule.confirmed` to `true`. Incomplete or invalid schedules keep the labelled
sample instead of publishing partial information.

The enquiry form is the default contact method. Publish an email or phone only
with permission: set `contact.approved` to `true`, choose `email` or `phone`, and
supply `contact.value`. Invalid contact details fall back to the enquiry form.
Do not place private learner information in this configuration.

A greeting is optional. Set `greeting.text`, `reviewer` and ISO `review_date`
only after Kaiārahi review. Unreviewed, invalid or future-dated wording is hidden.
Macrons are preserved. Keep each sentence at most 15 words.

## Acceptance checks

| Requirement | Verification |
| --- | --- |
| Public access and four key facts | Anonymous and both staff roles; no initial API dependency |
| 360px layout | Mobile browser, no horizontal overflow, long text wrapping |
| Readability | Body text at least 18px; axe WCAG A/AA; Lighthouse accessibility at least 90 |
| Plain English | Every rendered sentence at most 15 words; unit boundary cases |
| Missing address | Actual HTTP 404, friendly message and working home link |
| Privacy and review | No learner photos; permission and greeting validation unit tests |
| Existing workflows | Enquiry consent/submission and both staff login roles |

## Local commands

From `web`, install dependencies with `npm ci`, then:

```bash
npm run test:public-unit
npm run build
npm run test:public-ui
npm run test:public-a11y
npm run test:staff-ui
```

UI tests use locally installed Chrome by default. Set `BROWSER_CHANNEL=chromium`
to use Playwright Chromium after `npx playwright install chromium`.
Lighthouse can use a custom executable through `CHROME_PATH`.
The isolated UI runners start their own production server and mock staff
sessions; enquiry and login submissions are intercepted by browser tests.
They do not alter application databases.

Accessibility output is in `test-results/web/us009-home-lighthouse.json`,
`us009-enquiry-lighthouse.json`, `us009-login-lighthouse.json` and
`us009-accessibility-summary.json`. Read the summary before reusing reports.
Lighthouse measures the class information, enquiry and login pages; axe also checks the 404 page.
Check the current audit summary for each page score. The browser suite checks
separate routes, active navigation, back navigation and isolated form contents.

## Docker and full system checks

From the repository root:

```bash
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=public-unit test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=public-ui test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=public-a11y test-web
python3 tests/run_docker_tests.py --suite system
```

The system suite includes `tests/system/test_club_information.py`. Against an
already running test system, use:

```bash
BASE_URL=http://localhost:8080 pytest tests/system/test_club_information.py -q
```

Use the existing system-test dependency setup. Review console exit codes,
`test-results/web/summary.json`, web logs and system HTML/JUnit reports.
Docker was unavailable during implementation verification; run the Docker
commands in your Docker environment before deployment.

## Navigation regression check (26 Oct 2026)

The standalone login form and shared authentication layout match
`feature/v1.0/US_011`. Public navigation belongs only to the three public pages;
it is not added to the auth layout shared with account management. Teacher/coordinator home pages,
session handling and role destinations are unchanged. Tests verify route URLs,
current navigation, browser Back, direct links and absence of unrelated forms.
The class information, enquiry and login audits each scored 100/100.

Final checks: production build, 38 content unit tests, 24 public-page browser
tests, 5 Python browser checks and 27 existing Staff UI regression tests passed.
The five Python checks ran against the real Next frontend with the backend
unavailable; this does not replace full Docker integration tests.
