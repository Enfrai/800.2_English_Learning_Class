# Ako - System Tests: Teacher Access to Lesson Materials

| Version | Date        | Type     | Who     | Comment                                     |
| ------- | ----------- | -------- | ------- | ------------------------------------------- |
| 1.0     | 24 Oct 2026 | Creation | Sandhya | Manual scripts for AC1 to AC3 of the story  |

## 1. Purpose

Step-by-step scripts for the story "access shared lesson materials after
signing in" (the story after US-006; replace with its ID once confirmed). A
tester who did not build it runs them in a browser, records Pass or Fail, and
keeps a screenshot of each case as sprint evidence (NFR-09).

The same cases are automated in `tests/system/test_lesson_materials_page.py`
and `server/services/lesson/tests/test_materials_access.py`, and the session
rules in `server/services/user/tests/test_sessions.py`.

## 2. Before you start

- Start Ako with throwaway volumes, as in `tests/system/README.md` step 1.
- Use a desktop browser (Chrome, Edge or Firefox) at about 1280 px wide.
- Accounts: `teacher1` and `teacher2` (password `TeacherPass123!`) until
  US-001 adds real teacher accounts. Use a private window for `teacher2`.
- As `teacher1`, add a lesson "Bus trip" with a PDF `Bus timetable.pdf`, a
  picture `Bus stop.png` and a Word file `Notes.docx`.

## 3. Test cases

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| LM-01 (AC1) | Sign in as `teacher2` | The Lessons page opens. "Bus trip" is listed with its date, tags and 3 in the Files column. No Edit button for it | | |
| LM-02 (AC1) | Open "Bus trip" | The three files are listed with name and size. No Edit lesson, Delete lesson or Remove buttons | | |
| LM-03 (AC2) | Choose **Open** for `Bus timetable.pdf`, then for `Bus stop.png` | Each opens in a new tab and shows the file | | |
| LM-04 (AC2) | Choose **Download** for each of the three files | Each downloads with exactly its original name and opens in its usual program. `Notes.docx` has Download only, no Open | | |
| LM-05 (AC3) | Copy the address of the "Bus trip" page. Sign out. Paste the address | "Please log in to see this lesson". The page shows no lesson title and no file names | | |
| LM-06 (AC3) | Signed out, open <http://localhost:8080/lessons> and the lesson's `/edit` address | "Please log in…" only. No titles or file names | | |
| LM-07 (AC3) | Sign in as `teacher2`, then wait 31 minutes without using Ako. Open a lesson | "Please log in to see this lesson". After signing in again the lesson opens | | |
| LM-08 | Sign in as `teacher2`, use **Log out**, then press the browser's Back button and reload | "Please log in…". The old sign-in does not work again | | |
| LM-09 (US-008) | When US-008 is available, flag "Bus trip" as having Māori content | The list and the lesson page show "Māori content – not yet reviewed" until a coordinator records the review | | |

## 4. Result record

Copy the outcome to the Test Plan, section 7.3.

| Run date | Tester | Browser | Cases passed | Defects raised | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | / 9 | | |

Record a failed case as a defect with the case ID, the steps, what happened
and a screenshot (Test Plan section 7.2).
