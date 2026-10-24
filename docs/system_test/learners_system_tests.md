# Ako - System Tests: Learners Page (US-003)

| Version | Date        | Type     | Who | Comment                                  |
| ------- | ----------- | -------- | --- | ---------------------------------------- |
| 1.0     | 23 Oct 2026 | Creation | Pei | Manual scripts for ST-11 and related NTs |

## 1. Purpose

Step-by-step scripts for the Learners page system tests in the Test Plan
(section 5): ST-11 and the parts of NT-05, NT-06, NT-07, NT-08 and NT-10 that
concern this page. A tester who did not build US-003 runs them in a browser,
records Pass or Fail, and keeps a screenshot of each case as sprint evidence.

The same cases are automated in `tests/system/test_learners_page.py`. The
automated run supports the manual result; it does not replace it.

## 2. Before you start

- Start Ako with throwaway database volumes, as in `tests/system/README.md`
  step 1. Never use real learner data; all names below are made up.
- Use a desktop browser (Chrome, Edge or Firefox) at about 1280 px wide.
- Log in at <http://localhost:8080> as the demo coordinator
  (`demo` / `DemoPass123!`), then open <http://localhost:8080/learners>.
- Message text must match the UI design document, section 7, exactly.

## 3. Test cases

### 3.1 ST-11 Learner records

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| ST-11.1 | Choose **Add learner**. Enter First name `Aroha`, Family name `Ngata`, First language `Te reo Māori`, Phone or email `021 555 0101`. Choose **Save** | The form opens below the table with the cursor in First name. Within 2 seconds the list shows "Aroha Ngata" with Te reo Māori and the phone number, and "Learner saved" shows | | |
| ST-11.2 | Choose **Edit** for Aroha Ngata. Change First language to `English`. Choose **Save** | Within 2 seconds the row shows English. Name and phone number are unchanged. Still one Aroha Ngata | | |
| ST-11.3 | Choose **Add learner**. Enter `aroha` and `NGATA`. Choose **Save**, then **Cancel** in the warning | Warning "A learner with this name already exists." with **Cancel** and **Add anyway**. After Cancel the warning closes and no learner is added | | |
| ST-11.4 | Choose **Save** again, then **Add anyway** | Within 2 seconds the list shows two Aroha Ngata records | | |
| ST-11.5 | Choose **Add learner**. Leave both names empty. Choose **Save** | "First name is required" under First name and "Family name is required" under Family name, in red boxes. The cursor moves to First name. Nothing is added | | |
| ST-11.6 | Enter a first name of 101 characters and family name `Walker`. Choose **Save**. Then remove one character and choose **Save** | 101 characters: "Name must be 100 characters or fewer" under First name, nothing added. 100 characters: the learner is added | | |

### 3.2 Non-functional checks on the Learners page

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| NT-05.L | Open the Add learner form and read its fields | Only First name, Family name, First language and Phone or email. No date of birth, address, ID number, photo or ethnicity. The phone field hint says "Only if the learner agrees" | | |
| NT-06.L1 | Without the mouse: press Tab until **Add learner** is focused, press Enter, type a first name, Tab, type a family name, press Enter | Focus outline is visible at each step. The learner is added | | |
| NT-06.L2 | Run the browser's accessibility checker (for example Lighthouse) on the page with the form open | No errors. Body text 18 px, buttons and fields at least 44 px tall | | |
| NT-07.L | With at least 50 learners in the list, reload the page and time it | The list shows within 3 seconds | | |
| NT-08.L | Add a learner with first name `Robert` and family name `x'); DROP TABLE learners;--`. Reload the page | The learner is listed with exactly that text. No error; other learners are still listed | | |
| NT-10.L | Add `Tāne` `Māhina` with first language `Māori`. Reload the page | Macrons are shown exactly as typed | | |

### 3.3 Access

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| ACC.L1 | Choose **Log out**, then open <http://localhost:8080/learners> | The login page opens instead. No learner names are shown | | |
| ACC.L2 | Log in, then open the Learners page in a new browser tab | The list loads in the new tab | | |

## 4. Result record

Copy the outcome to the Test Plan, section 7.3 (row "US-003 Keep learner
records").

| Run date | Tester | Browser | Cases passed | Defects raised | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | / 16 | | |

Record a failed case as a defect with the case ID, the steps, what happened
and a screenshot (Test Plan section 7.2).
