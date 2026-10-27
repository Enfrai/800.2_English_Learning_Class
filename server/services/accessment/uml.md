# Accessment Service UML

Source baseline: `feature/v1.0/pre_release`, commit `f5e63dd0ccacffa4f8f0d6d920b04a94d51302a4`.

Diagrams describe the implemented application, not every possible requirement. GitHub renders the Mermaid fences directly. Use cases use a Mermaid flowchart with actor nodes, oval use cases and a system boundary because Mermaid has no native UML use-case syntax. Activity diagrams use decisions and explicit outcomes. Class diagrams distinguish actual classes from `table`, `module`, `type` and `component` representations. Only selected fields and operations are shown; function-based modules are not implemented service classes. Dashed dependencies represent calls or logical references, not database foreign keys.

## Scope and source map

The directory retains the name `accessment`; its public gateway prefix is `/api/access`. It owns dated class sessions, attendance, QR windows, historical corrections, attendance history, reports and learner material grants. Staff identity and learner records come from User Service. Lessons and material bytes come from Lesson Service.

| Area | Source |
| --- | --- |
| Sessions and lesson association | `class_sessions.py` |
| Current attendance and past corrections | `app.py`, `attendance.py`, `corrections.py` |
| QR opening, expiry, closing and learner sign-in | `checkin_management.py`, `checkin.py`, `app.py` |
| Learner material grants | `learner_materials.py` |
| History and exports | `attendance_history.py`, `attendance_reports.py`, `report_client.py` |
| External clients and local tables | `user_client.py`, `lesson_client.py`, `models.py`, `schema.py` |

## Use Case Diagram

```mermaid
flowchart TB
  staff["Actor: Teacher or Coordinator"]
  coord["Actor: Coordinator"]
  learner["Actor: Learner with classroom link"]
  subgraph access["Accessment Service"]
    sessions(["List, create, view or delete dated sessions"])
    link(["Associate or remove a session lesson"])
    attendance(["Mark, unmark or add learner and mark present today"])
    qr(["Open, display, print data or close QR window"])
    history(["View a learner attendance history"])
    correction(["Correct past attendance and read audit history"])
    reports(["Export attendance as CSV or PDF"])
    signin(["Validate classroom link and sign in by name"])
    materials(["List and download materials using a valid grant"])
  end
  staff --- sessions
  staff --- link
  staff --- attendance
  staff --- qr
  staff --- history
  coord --- correction
  coord --- reports
  learner --- signin
  learner --- materials
```

Staff includes both roles. Coordinator permissions for reports and corrections are checked by the service. Learners do not receive staff sessions. `/check` is a legacy demonstrator that compares a supplied role to `admin`; it is not the authorization mechanism for the business endpoints. QR printing itself is performed by the frontend using the returned SVG and URL.

## Activity Diagrams

### Session creation and lesson association

```mermaid
flowchart TD
  start(["Staff session operation"]) --> auth["Validate live staff identity through User Service"]
  auth --> action{"Action?"}
  action -->|Create dated class or start today| date{"Date supplied and not future?"}
  date -->|No| invalid["422"]
  date -->|Yes| insert["Insert unique session date or return existing session"]
  insert --> created(["Return session ID and created flag"])
  action -->|Link or unlink lesson| linked{"Nonempty lesson ID?"}
  linked -->|Yes| verify["Check live lesson through Lesson Service"]
  verify --> available{"Lesson available?"}
  available -->|No| missing["404 or service-unavailable error"]
  available -->|Yes| lock["Lock session and replace lesson link in transaction"]
  linked -->|No| lock
  lock --> saved(["Return updated class"])
  action -->|Delete| record["Lock session and count attendance records"]
  record --> empty{"No attendance records?"}
  empty -->|No| conflict["409 and keep session"]
  empty -->|Yes| delete["Delete grants, windows, link and session in transaction"]
  delete --> deleted(["204"])
```

A session has at most one lesson association and its date is unique. Starting today's class does not require Lesson Service availability. Session creation permits a past date; ordinary attendance marking rejects past dates. The shared helper does not itself reject a future or closed class; normal class creation rejects future dates, while QR sign-in applies additional today/status checks.

### Open QR window and learner sign-in

```mermaid
flowchart TD
  start(["Staff opens check-in"]) --> staff["Authenticate and lock class session"]
  staff --> today{"Today's class and not closed?"}
  today -->|No| reject["409"]
  today -->|Yes| existing{"Usable open window already exists?"}
  existing -->|Yes| reuse["Return existing QR URL and SVG"]
  existing -->|No| window["Validate origin and secret; close older windows"]
  window --> token["Derive token, store hash and cap expiry at four hours or local midnight"]
  token --> display["Return QR URL and SVG"]
  reuse --> scan["Learner opens classroom link"]
  display --> scan
  scan --> valid{"Token window open, unexpired and class today?"}
  valid -->|No| closed["Show check-in closed"]
  valid -->|Yes| names["Receive first and family name; check device and address limits"]
  names --> blocked{"Temporarily blocked?"}
  blocked -->|Yes| limit["429"]
  blocked -->|No| match["Ask User Service for active learner name match"]
  match --> found{"Exactly one learner?"}
  found -->|No| name["Show ask-teacher message; count unknown names but not ambiguous matches"]
  found -->|Yes| lock["Lock class and recheck current window expiry and closed state"]
  lock --> current{"Still valid?"}
  current -->|No| closed
  current -->|Yes| duplicate{"Already present?"}
  duplicate -->|Yes| already["409 without second attendance record"]
  duplicate -->|No| save["Mark present under window-opening staff member and issue material grant"]
  save --> finish(["Commit, set grant cookie and return signed-in message"])
```

Closing a window takes the same class lock as sign-in, so a stale validation cannot bypass closure. Unknown-name limits use keyed hashes, not stored raw addresses. Duplicate sign-in returns a conflict and does not issue a fresh material grant in that branch. Attendance and grant creation share the final local transaction; name matching occurs remotely first.

### Manual attendance and historical corrections

```mermaid
flowchart TD
  start(["Staff selects attendance action"]) --> auth["Authenticate and check learner through User Service"]
  auth --> day{"Class date?"}
  day -->|Today or later| manual{"Mark or unmark?"}
  manual -->|Mark| present["Insert or restore present record with unique session and learner pair"]
  present --> duplicate{"Already present?"}
  duplicate -->|Yes| conflict["409 with existing record"]
  duplicate -->|No| count["Commit and return current present count"]
  manual -->|Unmark| remove["Remove present record under nonpast-date rules"]
  remove --> count
  day -->|Past| role{"Coordinator correction request?"}
  role -->|No| denied["Reject ordinary editing of past attendance"]
  role -->|Yes| lock["Lock class and load previous attendance status"]
  lock --> changed{"Status changes?"}
  changed -->|No| unchanged["Return current result without new change entry"]
  changed -->|Yes| audit["Update or insert attendance and append old/new status audit"]
  audit --> count
```

The add-and-mark operation first creates or finds a learner through User Service, then records attendance locally. These are separate service transactions; learner creation is not rolled back if the later local attendance write fails. Corrections preserve history through append-only database triggers.

### History and attendance report

```mermaid
flowchart TD
  start(["Staff requests history or report"]) --> permission{"Request type and permission?"}
  permission -->|History by Teacher or Coordinator| learner["Validate learner and registration date through User Service"]
  learner --> dates["Validate optional start and end dates"]
  dates --> history["Collect eligible dated classes since registration through today"]
  history --> output["Map present rows to Present and missing or absent rows to Absent"]
  output --> result(["Return filtered history and counts, or no-records state"])
  permission -->|Report by Coordinator| range["Validate required reporting range and format"]
  range --> roster["Get roster from User Service and collect attendance totals"]
  roster --> format{"CSV or PDF?"}
  format -->|CSV| csv["Escape spreadsheet text and render CSV"]
  format -->|PDF| pdf["Render PDF with configured font"]
  csv --> file(["Return attachment without caching"])
  pdf --> file
  permission -->|Unauthorized| deny["401 or 403"]
```

History first determines whether any eligible attendance row exists for that learner; only then does it expand the class list, treating missing rows as absent. This is the implemented reporting interpretation, not proof of explicit absence entry at every class.

### Learner material access

```mermaid
flowchart TD
  start(["Learner requests materials"]) --> cookie{"Valid unexpired material grant cookie?"}
  cookie -->|No| signin["Require classroom sign-in again"]
  cookie -->|Yes| context["Resolve grant session and its current lesson link"]
  context --> linked{"Lesson linked?"}
  linked -->|No| empty["Return no materials message"]
  linked -->|Yes| remote["Call Lesson Service with internal key and linked lesson ID"]
  remote --> eligible{"Lesson, review and sharing checks pass?"}
  eligible -->|No| missing["Return empty/pending list, 404 or 503 as appropriate"]
  eligible -->|Yes| output(["Return eligible list or requested attachment"])
```

Grants last 24 hours, are stored only as token hashes, and are scoped to a session rather than an authenticated learner account. Downloads resolve the current lesson association and reapply sharing/review rules.

## Class Diagrams

### Actual request, domain and report classes

```mermaid
classDiagram
  class Staff {
    <<dataclass>>
    UUID id
    str display_name
    str role
  }
  class StaffRequest {
    <<dataclass>>
    str authorization
  }
  class OpenCheckin {
    <<dataclass>>
    UUID window_id
    UUID session_id
    date session_date
    datetime expires_at
    UUID opened_by
  }
  class AttendanceChange {
    <<Pydantic>>
    int present_count
  }
  class AttendanceOut {
    <<Pydantic>>
    UUID learner_id
    str status
    UUID recorded_by
    datetime recorded_at
  }
  class AddAndMarkOut {
    <<Pydantic>>
    bool learner_added
  }
  class AttendanceReport {
    <<dataclass>>
    date start
    date end
  }
  class ReportRow {
    <<dataclass>>
  }
  StaffRequest --> Staff : staff
  AttendanceChange --> "0..1" AttendanceOut : attendance
  AddAndMarkOut --|> AttendanceChange
  AttendanceReport "1" *-- "0..*" ReportRow : rows
```

### Local persistence and logical external references

```mermaid
classDiagram
  class class_sessions {
    <<table>>
    UUID id
    date session_date
    str status
    UUID created_by
  }
  class attendance_records {
    <<table>>
    UUID id
    UUID session_id
    UUID learner_id
    str status
    UUID recorded_by
  }
  class attendance_audits {
    <<table>>
    UUID attendance_id
    str old_status
    str new_status
    UUID corrected_by
    datetime created_at
  }
  class checkin_windows {
    <<table>>
    UUID id
    UUID session_id
    str token_hash
    datetime expires_at
    datetime closed_at
  }
  class session_lesson_links {
    <<table>>
    UUID session_id
    UUID lesson_id
  }
  class learner_material_grants {
    <<table>>
    str token_hash
    UUID session_id
    datetime expires_at
  }
  class signin_failures {
    <<table>>
    UUID id
    str key_hash
    datetime failed_at
  }
  class UserService {
    <<external>>
  }
  class LessonService {
    <<external>>
  }
  class_sessions "1" --> "0..*" attendance_records : session_id
  attendance_records "1" --> "0..*" attendance_audits : attendance_id
  class_sessions "1" --> "0..*" checkin_windows : session_id
  class_sessions "1" --> "0..1" session_lesson_links : session_id
  class_sessions "1" --> "0..*" learner_material_grants : session_id
  attendance_records ..> UserService : learner and staff UUIDs
  session_lesson_links ..> LessonService : logical lesson UUID
```

All local entities above are SQLAlchemy tables, not ORM classes. `(session_id, learner_id)` is unique. External learner, staff and lesson IDs have no cross-database foreign keys. `signin_failures` is intentionally not linked to learner or session identity. The session-to-lesson link may exist with a null lesson ID.
