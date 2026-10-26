# Ako - System Tests: Māori Content Review (US-008)

| Version | Date        | Type     | Who | Comment                                       |
| ------- | ----------- | -------- | --- | --------------------------------------------- |
| 1.0     | 26 Oct 2026 | Creation | Pei | Manual scripts for ST-09 and the review pages |

## 1. Purpose

Step-by-step scripts for the Māori content review system tests in the Test
Plan (section 5): ST-09 and the page parts of US-008 AC1 to AC5, NT-06 and
NT-10. A tester who did not build US-008 runs them in a browser, records Pass
or Fail, and keeps a screenshot of each case as sprint evidence.

The same cases are automated in `tests/system/test_review_pages.py` (pages)
and `tests/system/test_review_flow.py` (API checks a page cannot reach). The
automated run supports the manual result; it does not replace it.

The label wording and the review step are drafts until a Kaiārahi agrees
them (UI design document 6.10). These tests check that Ako does what the
draft says; they are not the Kaiārahi's approval.

## 2. Before you start

- Start Ako with throwaway volumes, as in `tests/system/README.md` step 1.
  Never use real data; all names below are made up.
- Use a desktop browser (Chrome, Edge or Firefox) at about 1280 px wide, and
  a private window for the teacher.
- Log in at <http://localhost:8080> as the demo coordinator
  (`demo` / `DemoPass123!`). Under **Account management**, add a teacher:
  display name `Test Teacher`, username `test_teacher`, and a temporary
  password you note down.
- In the private window, log in as `test_teacher`.
- Have a small PDF file ready, for example `handout.pdf`.
- Message text must match the UI design document, section 7, exactly.

## 3. Test cases

### 3.1 ST-09 Lesson with Māori content

| ID | Who | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- | --- |
| ST-09.1 (AC1) | Teacher | **Lessons** > **New lesson**. Title `Matariki and the new year`, any date, topic `culture`. Tick **Contains Māori content**. **Save lesson** | The lesson page shows an amber pill "Māori content – not yet reviewed". In **Lessons**, the same pill is under the title | | |
| ST-09.2 | Teacher | Open the lesson | No "Record a review" form | | |
| ST-09.3 (AC2) | Coordinator | Open the same lesson. Under "Record a review", enter `Te Aroha` and the date `14/10/2026`. **Save review** | "Review saved". The pill turns green: "Reviewed by Te Aroha, 14 Oct 2026" | | |
| ST-09.4 | Teacher | Reload the lesson page and the **Lessons** list | The same green pill on both | | |
| ST-09.5 (AC4) | Teacher | **Edit lesson**. Under "Add materials", choose `handout.pdf`. **Save lesson** | The file is listed. The pill is amber "Māori content – not yet reviewed" again, on the page and in the list | | |

### 3.2 Other US-008 checks

| ID | Who | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- | --- |
| RV-1 (AC3) | Coordinator | On a not yet reviewed lesson, leave **Reviewer name** empty, enter a date next year, **Save review** | "Reviewer name is required" under the name and "Review date cannot be in the future" under the date. The cursor is in Reviewer name. Reload: the pill is still amber | | |
| RV-2 (AC3) | Coordinator | Enter a name and leave the date empty. **Save review** | "Review date is required". The pill does not change | | |
| RV-3 | Teacher | New lesson without ticking **Contains Māori content** | No pill. The coordinator sees no review form on it | | |
| RV-4 | Teacher | On a reviewed lesson, **Edit lesson** | The box is ticked and the hint says "Unticking removes the recorded review." | | |
| RV-5 | Teacher | Untick **Contains Māori content**, **Save lesson**. Then open **Edit lesson** again | No pill. The box is not ticked | | |
| RV-6 | Coordinator | Open another teacher's lesson, **Edit lesson**, tick **Contains Māori content**, **Save lesson** | The amber pill shows; a coordinator may flag any lesson | | |

### 3.3 Non-functional checks

| ID | Who | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- | --- |
| NT-10.R (AC5) | Teacher, then coordinator | New lesson titled `Te reo Māori: ā ē ī ō ū`, ticked. The coordinator records a review by `Kiri Tāmaki-Ōtene` | The title and "Reviewed by Kiri Tāmaki-Ōtene, …" show every macron exactly as typed, in the list and on the page | | |
| NT-06.R1 | Coordinator | Without the mouse: Tab to Reviewer name, type a name, Tab to Review date, enter a date, press Enter | The review is saved and the pill turns green. The focus outline is visible at each step | | |
| NT-06.R2 | Both | Run the browser's accessibility checker (for example Lighthouse) on the lesson form and on the lesson page with the review form showing an error | No errors | | |
| NT-06.R3 | Coordinator | Open a lesson with the review form at phone width (about 375 px) | Everything fits; no sideways scrolling | | |

Exports (AC5, UT-48) are checked with the attendance reports when they are
built.

## 4. Result record

Copy the outcome to the Test Plan, section 7.3 (row "US-008 Flag Māori
content").

| Run date | Tester | Browser | Cases passed | Defects raised | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | / 15 | | |

Record a failed case as a defect with the case ID, the steps, what happened
and a screenshot (Test Plan section 7.2).
