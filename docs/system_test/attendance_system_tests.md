# Ako - System Tests: Attendance Sign-in (US-004)

| Version | Date        | Type     | Who | Comment                                     |
| ------- | ----------- | -------- | --- | ------------------------------------------- |
| 1.0     | 23 Oct 2026 | Creation | Pei | Manual scripts for ST-01 and related NTs    |
| 1.1     | 25 Oct 2026 | Update   | Pei | AT-4: past classes open the correction view |
| 1.2     | 26 Oct 2026 | Update   | Pei | Sessions opened on the Class sessions page  |

## 1. Purpose

Step-by-step scripts for the attendance (sign-in) page system tests in the
Test Plan (section 5): ST-01 and the parts of NT-01, NT-06, NT-07 and NT-10
that concern this page. A tester who did not build US-004 runs them in a
browser, records Pass or Fail, and keeps a screenshot of each case as sprint
evidence.

The same cases are automated in `tests/system/test_attendance_page.py`. The
automated run supports the manual result; it does not replace it.

## 2. Before you start

- Start Ako with throwaway database volumes, as in `tests/system/README.md`
  step 1. Never use real learner data; all names below are made up.
- Use a desktop browser (Chrome, Edge or Firefox) at about 1280 px wide.
- Log in at <http://localhost:8080> as the demo coordinator
  (`demo` / `DemoPass123!`). Teacher accounts come with US-002; both roles
  may take attendance.
- On the Learners page, add five learners: `Ana Class`, `Ben Class`,
  `Cy Class`, `Di Class`, `Ed Class`.
- On **Class sessions**, choose **Start today's class**. The class page
  opens at `http://localhost:8080/sessions/<today id>`; note the id. There
  is one session per date (US-014), so if today's class already exists it
  opens again instead of a new one.
- Back on **Class sessions**, choose **New class session**, enter
  yesterday's date and choose **Create or open class**. Note this id too.
- Open today's session at `http://localhost:8080/sessions/<today id>/attendance`
  (or choose **Attendance** on its row in **Class sessions**). If learners are
  already present from an earlier run, the counts below rise from that
  number instead of from 0.
- Message text must match the UI design document, section 7, exactly.

## 3. Test cases

### 3.1 ST-01 Teacher runs a class

"Start today's class" (US-014) is replaced by opening today's session as
above. ST-02 (reopen today's class) is tested with US-014.

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| ST-01.1 | Open today's session | The date shows under "Attendance". "Present 0 of N" shows, where N is the number of learners. "Class sessions" is underlined in the menu | | |
| ST-01.2 | Tick the 5 Class learners | Each box is ticked at once. Each row shows "Present" and the time. The count rises by 1 each time, to "Present 5 of N" | | |
| ST-01.3 | Under "Learner not on the list", enter `Hana` and `Newcomer`. Choose **Add and mark present** | "Hana Newcomer is added to the class list and marked present". Hana is in the list and ticked. Count 6. The cursor is back in First name | | |
| ST-01.4 | Untick Ana Class | The box clears, "Present" and the time disappear, count 5 | | |
| ST-01.5 | Reload the page. Then open the Learners page | Count still 5 and Ana is not ticked. Hana Newcomer is on the Learners page | | |
| ST-01.6 | Choose **Log out** | The login page opens | | |

### 3.2 Other US-004 checks

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| AT-1 | Enter `ana` and `CLASS`. Choose **Add and mark present** | "Ana Class is already on the class list and is now marked present". No second Ana Class row | | |
| AT-2 | Leave both names empty. Choose **Add and mark present** | "First name is required" and "Family name is required" under the fields | | |
| AT-3 | Open today's session in two browser windows. Tick Ben Class in the first window if he is not ticked. In the second window (not reloaded), tick Ben Class | "Already signed in" in Ben's row, next to the box. No second record: the count does not rise | | |
| AT-4 | Open yesterday's session | The coordinator's correction view opens: "You are correcting a past class. Every change is logged with your name and the time". No "Learner not on the list" form. Corrections and the teacher's view are tested in `corrections_system_tests.md` | | |
| AT-5 | Open `http://localhost:8080/sessions/00000000-0000-0000-0000-000000000000/attendance` | "Class session not found" | | |
| AT-6 | Choose **Log out**, then open today's session again | The login page opens instead. No names are shown | | |

### 3.3 Non-functional checks on the attendance page

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| NT-07.A | With at least 50 learners, reload today's session and time it (US-004 AC5) | The full list shows within 3 seconds | | |
| NT-01.A | Choose **Print this list**. Look at the print preview on A4 portrait in black and white | Readable, no name cut off, no menu bar and no "Learner not on the list" form | | |
| NT-06.A1 | Without the mouse: press Tab to a learner's tick box, press Space, wait for the count, press Space again | The focus outline stays on the box. The learner is ticked, then unticked | | |
| NT-06.A2 | Run the browser's accessibility checker (for example Lighthouse) | No errors | | |
| NT-10.A | Add `Tāne Māhina` with first language `Te reo Māori` on the Learners page, then open today's session | Macrons are shown exactly as typed | | |

## 4. Result record

Copy the outcome to the Test Plan, section 7.3 (row "US-004 Record
attendance by hand").

| Run date | Tester | Browser | Cases passed | Defects raised | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | / 17 | | |

Record a failed case as a defect with the case ID, the steps, what happened
and a screenshot (Test Plan section 7.2).
