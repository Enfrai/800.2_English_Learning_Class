# Ako - System Tests: Correct Past Attendance (US-015)

| Version | Date        | Type     | Who | Comment                                   |
| ------- | ----------- | -------- | --- | ----------------------------------------- |
| 1.0     | 25 Oct 2026 | Creation | Pei | Manual scripts for ST-04, ST-05 and NT-06 |

## 1. Purpose

Step-by-step scripts for the correction system tests in the Test Plan
(section 5): ST-04 (coordinator corrects attendance), ST-05 (teacher cannot
correct) and the correction parts of NT-06. A tester who did not build US-015
runs them in a browser, records Pass or Fail, and keeps a screenshot of each
case as sprint evidence.

The same cases are automated in `tests/system/test_corrections_page.py`. The
automated run supports the manual result; it does not replace it.

## 2. Before you start

- Start Ako with throwaway database volumes, as in `tests/system/README.md`
  step 1. Never use real learner data; all names below are made up.
- Use a desktop browser (Chrome, Edge or Firefox) at about 1280 px wide, and
  a private window for the teacher.
- Log in at <http://localhost:8080> as the demo coordinator
  (`demo` / `DemoPass123!`).
- On the Learners page, add three learners: `Mere Walker`, `Sione Taufa` and
  `Aroha Ngata`.
- Under **Account management**, add a teacher account: display name
  `Test Teacher`, username `test_teacher`, and a temporary password you note
  down.
- Create a class session for last week, and record that Mere Walker was
  ticked in that class. Until US-014 adds "Start today's class", run this
  from the `server` folder and note the session id it prints:

  ```bash
  MERE=$(docker compose exec -T postgres-user psql -U user_app -d userdb -tAqc \
    "SELECT id FROM learners WHERE first_name = 'Mere' AND family_name = 'Walker'")
  docker compose exec -T postgres-access psql -U access_app -d accessdb -tAqc \
    "WITH s AS (INSERT INTO class_sessions (id, session_date, created_by) VALUES
       (gen_random_uuid(), (now() AT TIME ZONE 'Pacific/Auckland')::date - 7, gen_random_uuid())
       RETURNING id)
     INSERT INTO attendance_records (id, session_id, learner_id, status, recorded_by)
       SELECT gen_random_uuid(), s.id, '$MERE', 'present', gen_random_uuid() FROM s
       RETURNING session_id"
  ```

- The page for that class is
  `http://localhost:8080/sessions/<session id>/attendance`.
- Message text must match the UI design document, section 7, exactly.

## 3. Test cases

### 3.1 ST-04 Coordinator corrects attendance

As the demo coordinator:

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| ST-04.1 | Open last week's class | "You are correcting a past class. Every change is logged with your name and the time". "Present 1 of N". Mere Walker is ticked. Tick boxes can be used. No "Learner not on the list" form. Under "Change history": "No changes yet." | | |
| ST-04.2 (AC1) | Tick Sione Taufa | The count rises by 1. Sione's row shows "Present", the time and a "Corrected" pill | | |
| ST-04.3 (AC2) | Untick Mere Walker | The count falls by 1. Mere's row shows "Corrected" and no longer "Present" | | |
| ST-04.4 (AC4) | Look at "Change history" | Two rows, oldest first: "Sione Taufa: Absent → Present", then "Mere Walker: Present → Absent". Each shows "Demo Coordinator" and today's date and time | | |
| ST-04.5 | Reload the page | The same ticks, pills, count and history as before the reload | | |
| CO-1 | Open today's class (any session dated today) and tick Aroha Ngata | Normal attendance page: no correction notice, no "Corrected" pill, no change history | | |

### 3.2 ST-05 Teacher cannot correct

In the private window, log in as `test_teacher` and open the same class:

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| ST-05.1 | Open last week's class | "Only a coordinator can correct past attendance". The names and "Present" are shown, with no tick boxes. Sione and Mere show "Corrected". No change history and no "Learner not on the list" form | | |
| ST-05.2 | Type the correction address: open the browser console (F12) on that page and run `fetch(location.pathname.replace("/sessions/", "/api/staff/access/sessions/").replace("/attendance", "/corrections"), {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({learner_id: "00000000-0000-0000-0000-000000000000", present: true})}).then(r => r.json()).then(console.log)` | `{detail: "You do not have permission"}`. Reload the page: the count has not changed | | |
| ST-05.3 | Open `http://localhost:8080/api/staff/access/sessions/<session id>/corrections` | `{"detail":"You do not have permission"}`, and no change history | | |

### 3.3 Non-functional checks on the correction view

As the demo coordinator, on last week's class:

| ID | Steps | Expected result | Result | Screenshot |
| --- | --- | --- | --- | --- |
| NT-06.C1 | Without the mouse: press Tab to Aroha Ngata's tick box and press Space | The focus outline stays on the box. The count rises by 1 and a new row appears in the change history | | |
| NT-06.C2 | Run the browser's accessibility checker (for example Lighthouse) on the coordinator's page and on the teacher's page | No errors | | |

## 4. Result record

Copy the outcome to the Test Plan, section 7.3 (row "US-015 Correct a past
attendance record").

| Run date | Tester | Browser | Cases passed | Defects raised | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | / 11 | | |

Record a failed case as a defect with the case ID, the steps, what happened
and a screenshot (Test Plan section 7.2).
