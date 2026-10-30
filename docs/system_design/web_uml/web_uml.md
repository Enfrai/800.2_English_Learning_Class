# Web Application UML

Diagrams describe the implemented application, not every possible requirement. GitHub renders the Mermaid fences directly. Use cases use a Mermaid flowchart with actor nodes, oval use cases and a system boundary because Mermaid has no native UML use-case syntax. Activity diagrams use decisions and explicit outcomes. Class diagrams distinguish actual classes from `table`, `module`, `type` and `component` representations. Only selected fields and operations are shown; function-based modules are not implemented service classes. Dashed dependencies represent calls or logical references, not database foreign keys.

## Scope and source map

Source paths in this document are relative to [web](../../../web).

The Next.js application presents public information, enquiries, staff login, staff administration, the lesson library, class sessions, attendance, QR management, learner material access and reports. It uses React function components and TypeScript data types. It does not own the backend databases.

| Area | Source |
| --- | --- |
| Public home, information and enquiries | `src/app/(auth)`, `src/components/club`, `src/components/enquiries` |
| Login, role navigation and session lifecycle | `src/middleware.ts`, `src/components/login-form.tsx`, `src/components/session-shell.tsx`, `src/lib/session.ts` |
| Staff sessions, learners, lessons and reports | `src/app/(staff)`, corresponding `src/components` folders |
| Public classroom sign-in and materials | `src/app/(public)`, `src/components/sign-in`, `src/components/materials` |
| Cookie-to-Bearer API adapters | `src/app/api/staff/access/[...path]/route.ts`, `src/app/api/staff/lesson/[...path]/route.ts`, `src/lib/api.ts` |
| UI styles and shared controls | `src/styles/ako`, `src/components/ako-controls.tsx` |

## Use Case Diagram

```mermaid
flowchart TB
  visitor["Actor: Visitor"]
  staff["Actor: Teacher or Coordinator"]
  coord["Actor: Coordinator"]
  learner["Actor: Classroom learner"]
  subgraph web["Web application"]
    public(["Open home, Class Information or Ask About Classes"])
    login(["Open Staff Login and authenticate"])
    learners(["Manage learners and view attendance history"])
    sessions(["Manage classes, lesson links and today's attendance"])
    lessons(["Browse, search, copy and manage permitted lessons"])
    qr(["Open, display, print or close check-in"])
    admin(["Manage Teacher accounts, import CSV and list enquiries"])
    reports(["Export attendance and correct past attendance"])
    review(["Record Māori content review"])
    signin(["Open QR link and submit learner name"])
    material(["View and download eligible class materials"])
    logout(["Log out or return to login after session ends"])
  end
  visitor --- public
  visitor --- login
  staff --- learners
  staff --- sessions
  staff --- lessons
  staff --- qr
  staff --- logout
  coord --- admin
  coord --- reports
  coord --- review
  learner --- signin
  learner --- material
```

The public navigation leads to separate content: `/`, `/class-information` and `/ask-about-classes`; Staff Login is presented on `/`. Staff landing pages are `/teacher` and `/coordinator`. The staff lesson editor additionally applies author/Coordinator permissions returned by the API. Feedback is not part of this baseline branch.

## Activity Diagrams

### Public navigation and staff authentication

```mermaid
flowchart TD
  start(["Open website"]) --> nav{"Navigation selection?"}
  nav -->|Class Information| info["Render configured public club information"]
  nav -->|Ask About Classes| enquiry["Render enquiry form and validate input"]
  enquiry --> post["Submit public enquiry to User Service"]
  post --> received(["Show success or validation/service error"])
  nav -->|Staff Login| login["Render login form on home route"]
  login --> submit["Send credentials to User Service"]
  submit --> ok{"Login accepted?"}
  ok -->|No| error["Show credential or lockout error"]
  error --> login
  ok -->|Yes| role{"Server role?"}
  role -->|Teacher| teacher["Navigate to /teacher"]
  role -->|Coordinator| coordinator["Navigate to /coordinator"]
  teacher --> shell["Load SessionShell and verify current session"]
  coordinator --> shell
  shell --> home(["Render role-specific staff navigation"])
```

### Protected page and session lifecycle

```mermaid
flowchart TD
  start(["Open protected staff route"]) --> middleware["Middleware verifies session using server cookie"]
  middleware --> valid{"Session check result?"}
  valid -->|Invalid| login["Return to login"]
  valid -->|Service failure| unavailable["503 without protected content"]
  valid -->|Valid| role{"Role permits route?"}
  role -->|No| forbidden["403 without protected page data"]
  role -->|Yes| shell["SessionShell loads identity and expiry"]
  shell --> event{"Browser event?"}
  event -->|Trusted pointer or keyboard input| activity["POST activity and update expiry"]
  activity --> shell
  event -->|Poll, focus or visibility restoration| observe["Read current session without renewing"]
  observe --> current{"Session remains valid?"}
  current -->|Yes| shell
  current -->|No| endSession["Clear client state and navigate to login"]
  event -->|Logout button| logout["POST logout and broadcast to other tabs"]
  logout --> endSession
  event -->|Expiry deadline or other-tab logout| endSession
```

Middleware excludes framework prefetch requests from its session check. This does not authorize data access: `SessionShell` and backend endpoints perform their own checks. Periodic reads do not count as activity. `SessionContext` supplies identity to staff child components.

### Staff feature request and error handling

```mermaid
flowchart TD
  start(["User edits a staff feature"]) --> form["Validate local fields and disable duplicate submission"]
  form --> request["Feature API module calls apiRequest or apiFile"]
  request --> target{"Backend family?"}
  target -->|User| direct["Call /api/user using same-origin staff cookie"]
  target -->|Access or Lesson| adapter["Route through Next staff adapter; convert cookie to Bearer header"]
  direct --> service["Backend validates live session, role and business rules"]
  adapter --> service
  service --> result{"Result?"}
  result -->|401| login["Return to login"]
  result -->|Validation, conflict or denied| error["Show field error, duplicate warning or permission message"]
  result -->|Network or service failure| retry["Show retryable error without assuming success"]
  result -->|Success| refresh["Update view or reload relevant data"]
  refresh --> done(["Show saved state or download attachment"])
```

Feature screens include learner creation/editing and CSV results; lesson creation/editing/copying and review; session lesson association and deletion; attendance marking/correction; history filtering; and CSV/PDF report download. Server permission checks remain authoritative even when UI controls are hidden or disabled.

### QR management and learner material journey

```mermaid
flowchart TD
  start(["Staff opens session detail"]) --> panel["CheckInPanel reads check-in state"]
  panel --> open["Request open window for today's active class"]
  open --> response{"Window available?"}
  response -->|No| error["Show configuration, permission or class-date error"]
  response -->|Yes| display["Display SVG, URL and expiry; optionally print document"]
  display --> learner["Learner scans QR and opens /sign-in/token"]
  learner --> validate["SignInScreen validates token through Accessment"]
  validate --> valid{"Link open?"}
  valid -->|No| closed["Show check-in closed and ask teacher"]
  valid -->|Yes| form["Learner enters first and family name"]
  form --> submit["Submit name and random device ID"]
  submit --> result{"Sign-in result?"}
  result -->|Unknown or ambiguous name, blocked, duplicate or closed| message["Show specific safe message and teacher guidance"]
  result -->|Success| grant["Browser receives HttpOnly material grant cookie"]
  grant --> materials["Load MaterialsScreen and request linked shared files"]
  materials --> state{"Materials response?"}
  state -->|Available| files["Show file links and download selected material"]
  state -->|Empty or pending review| pending["Show returned availability message"]
  state -->|Grant invalid or expired| again["Ask learner to scan and sign in again"]
```

Closing or expiring check-in prevents later sign-in; an already issued material grant has its own expiry. Materials also have a standalone `/materials` route. A duplicate attendance response does not establish a new material authorization cookie.

## Class Diagrams

### React components and API modules

These are component/module dependencies represented in class-diagram notation, not JavaScript class inheritance. Route page functions compose these components. Only major dependencies are shown.

```mermaid
classDiagram
  class SessionShell {
    <<component>>
  }
  class SessionContext {
    <<context>>
  }
  class SessionListScreen {
    <<component>>
  }
  class SessionDetailScreen {
    <<component>>
  }
  class CheckInPanel {
    <<component>>
  }
  class AttendanceScreen {
    <<component>>
  }
  class SessionLesson {
    <<component>>
  }
  class ApiModule {
    <<module>>
    apiRequest()
    apiFile()
  }
  class ClassSessionsApi {
    <<module>>
    listClassSessions()
    startToday()
    linkClassLesson()
    deleteClassSession()
  }
  SessionShell ..> SessionContext : provides Session value
  SessionDetailScreen ..> CheckInPanel : renders
  AttendanceScreen ..> SessionLesson : renders
  SessionListScreen ..> ClassSessionsApi : calls
  SessionDetailScreen ..> ClassSessionsApi : calls
  AttendanceScreen ..> ApiModule : via attendance-api
  CheckInPanel ..> ApiModule : via checkin-management-api
  SessionLesson ..> ApiModule : reads and updates lesson link
  ClassSessionsApi ..> ApiModule : calls
```

```mermaid
classDiagram
  class LearnersScreen {
    <<component>>
  }
  class LearnerForm {
    <<component>>
  }
  class CsvUpload {
    <<component>>
  }
  class AttendanceHistoryScreen {
    <<component>>
  }
  class LessonsScreen {
    <<component>>
  }
  class LessonEditor {
    <<component>>
  }
  class LessonDetail {
    <<component>>
  }
  class ReviewForm {
    <<component>>
  }
  class SignInScreen {
    <<component>>
  }
  class MaterialsScreen {
    <<component>>
  }
  class AttendanceReports {
    <<component>>
  }
  class FeatureApiModules {
    <<moduleGroup>>
    learners_api
    lessons_api
    attendance_history_api
    attendance_reports_api
    checkin_api
    materials_api
  }
  LearnersScreen ..> LearnerForm : renders
  LearnersScreen ..> CsvUpload : Coordinator view
  LearnersScreen ..> FeatureApiModules : calls
  AttendanceHistoryScreen ..> FeatureApiModules : calls
  LessonsScreen ..> FeatureApiModules : calls
  LessonEditor ..> FeatureApiModules : calls
  LessonDetail ..> ReviewForm : renders
  LessonDetail ..> FeatureApiModules : calls
  ReviewForm ..> FeatureApiModules : calls
  SignInScreen ..> MaterialsScreen : success view
  SignInScreen ..> FeatureApiModules : calls
  MaterialsScreen ..> FeatureApiModules : calls
  AttendanceReports ..> FeatureApiModules : calls
```

`FeatureApiModules` is a diagram grouping of separate files, not an exported symbol. PublicFrame/PublicNavigation, LoginForm, StaffManagement and CoordinatorEnquiries supply the remaining public/authentication/administration views.

### TypeScript data contracts and actual error classes

```mermaid
classDiagram
  class Session {
    <<type>>
    string user_id
    string display_name
    Role role
    number expiresAt
  }
  class ClassSession {
    <<type>>
    string id
    string session_date
    string lesson_id
    number attendance_count
    number present_count
    boolean can_delete
  }
  class SessionList {
    <<type>>
    string today
  }
  class Lesson {
    <<type>>
    string id
    string title
    boolean can_edit
    boolean has_maori_content
    string review_status
  }
  class LessonMaterial {
    <<typeAliasForLessonsMaterial>>
    string id
    string lesson_id
    string file_name
    boolean share_with_learners
  }
  class AttendanceList {
    <<type>>
    string session_date
    boolean editable
    number present_count
  }
  class AttendanceRecord {
    <<type>>
    string learner_id
    string status
    string recorded_by
    string recorded_at
  }
  SessionList "1" *-- "0..*" ClassSession : sessions
  Lesson "1" *-- "0..*" LessonMaterial : materials
  AttendanceList "1" *-- "0..*" AttendanceRecord : records
  ClassSession ..> Lesson : nullable lesson_id
```

`LessonMaterial` disambiguates the `Material` type in `lessons-api.ts` from the smaller public `Material` type in `materials-api.ts`; it is a diagram alias. Nullable values are simplified in the boxes; see the source types for exact unions. Data types represent API payloads, not persistent frontend entities.

```mermaid
classDiagram
  class Error
  class LoginRequiredError
  class RequestFailedError
  class ClassSessionError {
    string field
    number status
  }
  class LessonError
  class AlreadySignedInError {
    AttendanceRecord record
  }
  class LearnerFieldError
  class DuplicateNameError
  class HistoryError {
    number status
    string field
  }
  class ReportError
  Error <|-- LoginRequiredError
  Error <|-- RequestFailedError
  Error <|-- ClassSessionError
  Error <|-- LessonError
  Error <|-- AlreadySignedInError
  Error <|-- LearnerFieldError
  Error <|-- DuplicateNameError
  Error <|-- HistoryError
  Error <|-- ReportError
```

Actual error classes translate backend statuses into UI behavior. Additional small error classes in the feature API files are omitted for readability. This diagram does not imply that the functional screens inherit from these classes.
