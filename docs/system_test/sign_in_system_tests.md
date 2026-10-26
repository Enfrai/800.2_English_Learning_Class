# Ako - System Tests: Learner QR Sign-in (US-012)

| Version | Date        | Type     | Who | Comment                                          |
| ------- | ----------- | -------- | --- | ------------------------------------------------ |
| 1.0     | 25 Oct 2026 | Creation | Pei | Manual scripts for the ST-14 sign-in part and NTs |
| 1.1     | 26 Oct 2026 | Update   | Pei | Today's class started on the Class sessions page  |
| 1.2     | 26 Oct 2026 | Update   | Pei | Full ST-14: check-in on the class page, materials |

## 1. Purpose

Step-by-step scripts for the learner sign-in system tests in the Test Plan
(section 5): ST-14 from the teacher opening check-in to closing it (US-011,
US-012, US-013), US-012 AC1 to AC6, and the sign-in parts of NT-06 and NT-11. A tester who did not build US-012 runs them, records
Pass or Fail, and keeps a screenshot of each case as sprint evidence.

The same cases are automated in `tests/system/test_sign_in_page.py`. The
automated run supports the manual result; it does not replace it.

Printing the QR code, expiry after four hours and the check-in API are
tested in `qr_checkin_system_tests.md` (US-011); the materials page on its own
in `materials_system_tests.md` (US-013).

## 2. Before you start

- Start Ako with throwaway database volumes, as in `tests/system/README.md`
  step 1. Never use real learner data; all names below are made up.
- Use two phones, or a desktop browser in phone view at 360 px wide (for
  example Chrome DevTools device mode). A second phone means a separate
  browser or a private window.
- On a laptop, log in as the demo coordinator (`demo` / `DemoPass123!`) and
  add learners on the Learners page: `Aroha Ngata`, `Tāne Māhina`, and
  `Mere Walker` twice (choose **Add anyway** the second time).
- Under **Account management**, add a teacher account (for example
  `test_teacher`) and log in as that teacher in a private window. ST-14 is a
  teacher's task.
- On **Lessons**, add a lesson with a small PDF, tick **Share with learners**
  for the file, and leave **Contains Māori content** unticked.
- On **Class sessions**, choose **Start today's class** (US-014). The class
  page opens at `http://localhost:8080/sessions/<session id>`. If today's
  class already exists, it opens again instead of a new one. Under **Class
  lesson**, choose the lesson you added.
- To scan with a real phone, the phone must reach this computer: set
  `AKO_BIND_ADDRESS`, `CHECKIN_PUBLIC_ORIGIN` and `CHECKIN_TOKEN_SECRET` as in
  `qr_checkin_system_tests.md`, "Phone access and Docker". With a desktop
  browser in phone view, open the link under the QR code instead of scanning.
- The teacher's list is `http://localhost:8080/sessions/<session id>/attendance`.
- Message text must match the UI design document, section 7, exactly.

## 3. Test cases

### 3.1 ST-14 QR check-in, from opening to closing

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| ST-14.1 (US-011) | As the teacher, open today's class page. Under **QR check-in**, choose **Open check-in** | "Check-in is open", a QR code, the class date and a link under the code | | |
| ST-14.2 | On the phone, scan the code (or open the link) | "Sign in to class" and today's date. No login and no staff menu | | |
| ST-14.3 | Enter `Aroha` `Ngata` and choose **Sign in**. On the laptop, open the teacher's list | "You are signed in". Within 10 seconds Aroha Ngata shows Present on the teacher's list | | |
| ST-14.4 (US-013) | On the phone, choose **Lesson materials**, then **Download** for the PDF | The materials page lists the shared PDF. It downloads with its original name | | |
| ST-14.5 (US-011) | As the teacher, on the class page choose **Close check-in** | "Check-in is closed". The QR code is gone | | |
| ST-14.6 | On the phone, scan the code again (or reload the sign-in link) | "Check-in is closed. Please ask the teacher". No form | | |
| ST-14.7 | On the phone, open `http://localhost:8080/materials` (or the computer's address) again | The materials are still listed: closing check-in does not take them away | | |

For the cases below, open check-in again on the class page and use the new
code.

### 3.2 US-012 acceptance criteria

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| SI-1 (AC2) | Enter `tane` `mahina` (no macrons) | "You are signed in". A **Lesson materials** link is shown; the materials page is tested in `materials_system_tests.md` (US-013) | | |
| SI-2 (AC3) | Enter `Nobody` `Here` | "We could not find that name. Please ask the teacher". The cursor goes back to First name | | |
| SI-3 | Enter `Mere` `Walker` (two learners share this name) | "We could not find that name. Please ask the teacher". The teacher ticks the right Mere on the attendance page | | |
| SI-4 (AC4) | Reload the link and enter `Tāne` `Māhina` again | "Already signed in". The teacher's list still shows Tāne once | | |
| SI-5 (AC5) | Open `http://localhost:8080/sign-in/made-up-token` | "Check-in is closed. Please ask the teacher" | | |
| SI-6 | Leave both names empty and choose **Sign in** | "First name is required" and "Family name is required" under the fields | | |

### 3.3 Non-functional checks

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| NT-06.S1 (AC6) | At 360 px wide, look at the page and scroll sideways | No sideways scrolling. Text is large (18 px) and the Sign in button is at least 44 px tall | | |
| NT-06.S2 | Run the browser's accessibility checker on the page | No errors | | |
| NT-11.S | On phone A, enter 10 made-up names one after another, then a real name. Then on phone B (same Wi-Fi), enter a real name | Phone A: "Too many tries. Please ask the teacher". Phone B: "You are signed in" | | |

## 4. Result record

Copy the outcome to the Test Plan, section 7.3 (row "US-012 Sign in by
scanning the QR code").

| Run date | Tester | Phone or browser | Cases passed | Defects raised | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | / 16 | | |

Record a failed case as a defect with the case ID, the steps, what happened
and a screenshot (Test Plan section 7.2).
