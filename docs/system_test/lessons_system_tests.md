# Ako - System Tests: Lessons (US-006)

| Version | Date        | Type     | Who     | Comment                                        |
| ------- | ----------- | -------- | ------- | ---------------------------------------------- |
| 1.0     | 23 Oct 2026 | Creation | Sandhya | Manual scripts for ST-10, US-006 AC1–AC6, UA-04 |

## 1. Purpose

Step-by-step scripts for the lesson system tests in the Test Plan: ST-10
(lesson file rules), the six US-006 acceptance criteria, the browser side of
UT-42 (only the author or a coordinator can change a lesson), NFR-10 (macrons)
and the user acceptance task UA-04. A tester who did not build US-006 runs
them in a browser, records Pass or Fail, and keeps a screenshot of each case
as sprint evidence (NFR-09).

The same cases are automated in `tests/system/test_lessons_page.py`, and the
unit cases UT-39 to UT-43 and UT-70 in `server/services/lesson/tests`. The
automated run supports the manual result; it does not replace it.

## 2. Before you start

- Start Ako with throwaway volumes, as in `tests/system/README.md` step 1
  (include `LESSON_FILES_VOLUME`). Never use real lesson material.
- Use a desktop browser (Chrome, Edge or Firefox) at about 1280 px wide.
- Accounts: test teachers `teacher1` and `teacher2` (password
  `TeacherPass123!`), and the demo coordinator (`demo` / `DemoPass123!`).
  Use a private window for the second account, so both stay logged in.
- Prepare these files: a PDF of about 2 MB named `Bus timetable.pdf`, a PDF of
  exactly 10 MB, a file of 10.1 MB, a file under 1 KB, and any `.exe` file.
  To make test files of an exact size on Windows:
  `fsutil file createnew big.pdf 10590617` (the 10.1 MB file; a made-up file
  is fine for the refused cases).
- Messages must match the UI design document, section 7, exactly.

## 3. Test cases

### 3.1 Save, list, edit and delete (US-006 AC1, AC2, AC5, AC6)

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| LS-01 (AC1) | Log in as `teacher1`. Choose **Lessons**, then **Add lesson**. Enter Title `Catching the bus`, Lesson date 21 Oct 2026, tick **Transport** and **Health**. Choose **Save** | The lesson page shows "Lesson saved". Choose **All lessons**: the list shows "Catching the bus" with 21 Oct 2026 and the chips Transport and Health | | |
| LS-02 (AC2) | Choose **Add lesson**. Leave Title empty, choose a date and a tag. Choose **Save** | "Title is required" under Title in a red box. The cursor moves to Title. Nothing is added to the list | | |
| LS-03 | Choose **Add lesson**. Enter a title only. Choose **Save** | "Lesson date is required" under Lesson date and "Choose at least one topic tag" under Topic tags. Nothing is saved | | |
| LS-04 (AC5) | Open "Catching the bus" (with the file from LS-06 attached). Choose **Edit lesson**, change the title to `Catching the train`, choose **Save** | "Lesson saved". The title is "Catching the train", the date is still 21 Oct 2026 and the file is still listed. The list shows the new title | | |
| LS-05 (AC6) | Open "Catching the train". Choose **Delete lesson**, read the warning, choose **Cancel**. Then choose **Delete lesson** again and **Yes, delete** | Cancel: nothing changes. Yes, delete: the list opens with "Lesson deleted" and the lesson is gone. Opening the old lesson address shows "This lesson was not found" | | |

### 3.2 Files (US-006 AC3, AC4, ST-10)

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| LS-06 (AC3) | On a new lesson, choose `Bus timetable.pdf` under Files. Leave **Share with learners** unticked. Choose **Save**. On the lesson page choose **Download** | The file is listed with its size and an unticked Share with learners box. The downloaded file is named `Bus timetable.pdf` and opens | | |
| LS-07 (AC3) | Attach the exactly 10 MB PDF and save | Accepted and listed | | |
| ST-10.1 (AC4) | On **Add lesson**, enter a title, date and tag. Choose the 10.1 MB file | "big.pdf: Files must be PDF, DOCX, JPG or PNG, from 1 KB to 10 MB" under Files. Title, date and tags are still filled in. The file is not listed | | |
| ST-10.2 (AC4) | On the same form, choose the `.exe` file, then the file under 1 KB | The same rule message names each file. Title, date and tags are still filled in | | |
| LS-08 | Before downloading in LS-06, open the same lesson as `teacher2` and choose **Download** | `teacher2` can download the file with the same name, because lessons are shared | | |
| LS-09 (AC6) | In LS-05, note a file's download before deleting. After deleting, try the old lesson address again as `teacher2` | The lesson and its files can no longer be opened or downloaded | | |

### 3.3 Who can change a lesson (UT-42 in the browser)

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| PR-01 | As `teacher2`, open the Lessons list | Lessons by `teacher1` are listed with **Open** but no **Edit** | | |
| PR-02 | As `teacher2`, open a lesson by `teacher1` | No **Edit lesson**, **Delete lesson** or **Remove** buttons. The Share with learners boxes cannot be changed | | |
| PR-03 | As `teacher2`, type the address `/lessons/<id>/edit` of that lesson | "You do not have permission" and no form | | |
| PR-04 | Log in as the coordinator `demo`. Open the same lesson | **Edit lesson** and **Delete lesson** are shown and editing the title works | | |

### 3.4 Non-functional checks

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| NT-10.LS | Add a lesson titled `Te reo Māori` with a file named `Māori kai.pdf`. Reload the list and the lesson page, then download the file | Macrons are shown exactly as typed, and the downloaded file is named `Māori kai.pdf` | | |
| NT-06.LS1 | Without the mouse: Tab through the Add lesson form, tick a tag with Space, press Enter on Save | Focus outline is visible at each step. The lesson is saved | | |
| NT-06.LS2 | Run the browser's accessibility checker on the form with error messages showing, and on a lesson page | No errors. Buttons and fields at least 44 px tall | | |
| ACC.LS | Log out, then open <http://localhost:8080/lessons> | "Please log in to see the lessons" with a Log in link. No lesson titles are shown | | |

### 3.5 User acceptance (UA-04, run by the Story Owner)

| ID | Task given to the teacher | Expected result | Result | Time |
| --- | --- | --- | --- | --- |
| UA-04 | "Add a lesson about using the bus with a PDF and two topic tags" | Lesson saved with the file and both tags, within about 4 minutes, without help | | |

## 4. Result record

Copy the outcome to the Test Plan, section 7.3 (row "US-006 Create a lesson").

| Run date | Tester | Browser | Cases passed | Defects raised | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | / 20 | | |

Record a failed case as a defect with the case ID, the steps, what happened
and a screenshot (Test Plan section 7.2).
