# Ako - System Tests: Learner QR Sign-in (US-012)

| Version | Date        | Type     | Who | Comment                                          |
| ------- | ----------- | -------- | --- | ------------------------------------------------ |
| 1.0     | 25 Oct 2026 | Creation | Pei | Manual scripts for the ST-14 sign-in part and NTs |

## 1. Purpose

Step-by-step scripts for the learner sign-in system tests in the Test Plan
(section 5): the sign-in part of ST-14, US-012 AC1 to AC6, and the sign-in
parts of NT-06 and NT-11. A tester who did not build US-012 runs them, records
Pass or Fail, and keeps a screenshot of each case as sprint evidence.

The same cases are automated in `tests/system/test_sign_in_page.py`. The
automated run supports the manual result; it does not replace it.

Not covered yet: opening, printing and closing check-in from the teacher's
page (US-011) and the materials page after sign-in (US-013). Until US-011 is
built, check-in is opened and closed with the commands below.

## 2. Before you start

- Start Ako with throwaway database volumes, as in `tests/system/README.md`
  step 1. Never use real learner data; all names below are made up.
- Use two phones, or a desktop browser in phone view at 360 px wide (for
  example Chrome DevTools device mode). A second phone means a separate
  browser or a private window.
- On a laptop, log in as the demo coordinator (`demo` / `DemoPass123!`) and
  add learners on the Learners page: `Aroha Ngata`, `Tāne Māhina`, and
  `Mere Walker` twice (choose **Add anyway** the second time).
- Create today's class and open check-in. From the `server` folder:

  ```bash
  docker compose exec -T postgres-access psql -U access_app -d accessdb -tAqc \
    "INSERT INTO class_sessions (id, session_date, created_by) VALUES
     (gen_random_uuid(), (now() AT TIME ZONE 'Pacific/Auckland')::date, gen_random_uuid())
     RETURNING id"
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

  Note the session id and the token, then open check-in with them:

  ```bash
  TOKEN=<token>; SESSION=<session id>
  HASH=$(printf %s "$TOKEN" | shasum -a 256 | cut -d' ' -f1)
  docker compose exec -T postgres-access psql -U access_app -d accessdb -c \
    "INSERT INTO checkin_windows (id, session_id, token_hash, opened_by, expires_at)
     VALUES (gen_random_uuid(), '$SESSION', '$HASH', gen_random_uuid(), now() + interval '3 hours')"
  ```

- The learner's link is `http://localhost:8080/sign-in/<token>`. The teacher's
  list is `http://localhost:8080/sessions/<session id>/attendance`.
- Message text must match the UI design document, section 7, exactly.

## 3. Test cases

### 3.1 ST-14 QR check-in (sign-in part)

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| ST-14.1 | On the phone, open the learner's link | "Sign in to class" and today's date. No login and no staff menu | | |
| ST-14.2 | Enter `Aroha` `Ngata` and choose **Sign in**. On the laptop, open the teacher's list | "You are signed in". Within 10 seconds Aroha Ngata shows Present on the teacher's list | | |
| ST-14.3 | Close check-in: `docker compose exec -T postgres-access psql -U access_app -d accessdb -c "UPDATE checkin_windows SET closed_at = now() WHERE token_hash = '$HASH'"`. Reload the learner's link | "Check-in is closed. Please ask the teacher". No form | | |

Open a new check-in (section 2) for the cases below.

### 3.2 US-012 acceptance criteria

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| SI-1 (AC2) | Enter `tane` `mahina` (no macrons) | "You are signed in". "Lesson materials (later)" is shown greyed and cannot be used | | |
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
| | | | / 12 | | |

Record a failed case as a defect with the case ID, the steps, what happened
and a screenshot (Test Plan section 7.2).
