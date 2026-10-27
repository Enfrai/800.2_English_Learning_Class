# User Service UML

Source baseline: `feature/v1.0/pre_release`, commit `f5e63dd0ccacffa4f8f0d6d920b04a94d51302a4`.

Diagrams describe the implemented application, not every possible requirement. GitHub renders the Mermaid fences directly. Use cases use a Mermaid flowchart with actor nodes, oval use cases and a system boundary because Mermaid has no native UML use-case syntax. Activity diagrams use decisions and explicit outcomes. Class diagrams distinguish actual classes from `table`, `module`, `type` and `component` representations. Only selected fields and operations are shown; function-based modules are not implemented service classes. Dashed dependencies represent calls or logical references, not database foreign keys.

## Scope and source map

The User Service owns staff authentication, teacher account administration, learner records, CSV import and public enquiries. Public club information is frontend content. Learners have no login accounts. Enquiries do not automatically create learners.

| Area | Source |
| --- | --- |
| Login, current session, activity and logout | `app.py`, `auth.py`, `security.py` |
| Teacher account administration | `staff.py`, `staff_service.py`, `init_coordinator.py` |
| Learners and CSV import | `learners.py`, `learner_csv.py`, `learner_import.py` |
| Public enquiries and reporting roster | `enquiries.py`, `report_roster.py` |
| Local database tables | `models.py` |

## Use Case Diagram

Staff means Teacher or Coordinator. Coordinator-specific operations are attached separately. Internal clients must satisfy the authentication of the corresponding endpoint.

```mermaid
flowchart TB
  staff["Actor: Teacher or Coordinator"]
  coord["Actor: Coordinator"]
  visitor["Actor: Visitor"]
  client["Actor: Accessment or Lesson Service"]
  subgraph user["User Service"]
    auth(["Log in, read session, renew on activity and log out"])
    learners(["List, search, create and edit learners"])
    teachers(["List, create, rename and deactivate teachers"])
    csv(["Import learners from CSV"])
    enquiry(["Submit a class enquiry"])
    inbox(["List enquiries with pagination"])
    identity(["Verify staff identity and role"])
    match(["Match learner name for QR sign-in"])
    roster(["Supply attendance report roster"])
  end
  staff --- auth
  staff --- learners
  coord --- teachers
  coord --- csv
  coord --- inbox
  visitor --- enquiry
  client --- identity
  client --- match
  client --- roster
```

`/me` validates a live staff session. `/internal/learners/match` requires the internal key. Reporting roster access is Coordinator-only. Teacher administration does not allow changing a Coordinator account or assigning arbitrary roles. The coordinator bootstrap command is an operator task, not a public registration use case.

## Activity Diagrams

### Staff login and session lifecycle

```mermaid
flowchart TD
  start(["Login request"]) --> origin{"Allowed request origin?"}
  origin -->|No| deny["Reject request"]
  origin -->|Yes| lookup["Lock matching user row"]
  lookup --> active{"User exists and is active?"}
  active -->|No| invalid["Return invalid credentials"]
  active -->|Yes| locked{"Lockout still active?"}
  locked -->|Yes| wait["Return lockout response"]
  locked -->|No| password{"Password valid?"}
  password -->|No| count["Commit failed attempt count and lockout if threshold reached"]
  count --> invalid
  password -->|Yes| replace["Reset failures and delete prior sessions"]
  replace --> token["Create random token and store only its hash with expiry"]
  token --> commit["Commit and set session cookie"]
  commit --> later{"Later request"}
  later -->|Read protected resource| validate["Check active account, token, revocation and expiry"]
  later -->|Trusted user activity| renew["Validate and extend live session expiry"]
  later -->|Logout| revoke["Revoke session and clear cookie"]
  validate --> result(["Return identity or 401"])
  renew --> result
  revoke --> done(["Logged out"])
```

A new login replaces the old session. Reading a session does not renew it. Mutation protection and cookie configuration are implemented in `security.py` and `auth.py`; database-derived roles remain authoritative.

### Learner creation and CSV import

```mermaid
flowchart TD
  start(["Staff learner operation"]) --> auth{"Live staff session?"}
  auth -->|No| reject["401"]
  auth -->|Yes| mode{"Manual entry or CSV?"}
  mode -->|Manual| fields["Validate learner fields"]
  fields --> valid{"Valid?"}
  valid -->|No| errors["Return field errors"]
  valid -->|Yes| duplicate{"Same-name learner found?"}
  duplicate -->|Yes| confirm{"Explicit namesake confirmation?"}
  confirm -->|No| warn["Return duplicate warning"]
  confirm -->|Yes| insert["Insert learner and commit"]
  duplicate -->|No| insert
  mode -->|CSV| coord{"Coordinator?"}
  coord -->|No| forbidden["403"]
  coord -->|Yes| parse["Check size, filename, UTF-8, headers and CSV structure"]
  parse --> structure{"Whole-file structure valid?"}
  structure -->|No| errors
  structure -->|Yes| classify["Classify valid rows, row errors and file duplicates"]
  classify --> lock["Begin transaction, take import lock and recheck Coordinator session"]
  lock --> batch["Insert valid nonduplicate rows and skip database duplicates"]
  batch --> ok{"Database writes succeed?"}
  ok -->|No| rollback["Roll back batch and report no imports"]
  ok -->|Yes| report["Commit and return imported count, duplicates and row errors"]
```

Malformed file structure rejects the file. Field-invalid rows can be reported while valid rows are imported together. The advisory lock serializes CSV imports across replicas; it is not a global lock on manual learner writes.

### Teacher administration and public enquiry

```mermaid
flowchart TD
  start(["Request"]) --> kind{"Operation?"}
  kind -->|Teacher administration| session["Authenticate Coordinator"]
  session --> locks["Lock relevant users and recheck live actor session"]
  locks --> allowed{"Creation or permitted Teacher target?"}
  allowed -->|No| deny["Return permission, conflict or not-found error"]
  allowed -->|Yes| change["Create, rename or deactivate Teacher"]
  change --> commit["Commit account change and invalidate sessions when deactivating"]
  kind -->|Public enquiry| validate["Validate name, contact and optional message"]
  validate --> valid{"Valid submission?"}
  valid -->|No| error["Return validation error"]
  valid -->|Yes| store["Store enquiry with new status"]
  store --> received(["Return submission acknowledgement"])
  kind -->|Enquiry listing| permission["Require Coordinator and validate pagination bounds"]
  permission --> listing(["Return stored enquiries"])
```

Enquiry status values exist in storage, but this branch does not expose a status-update workflow. The diagram therefore shows submission and listing only.

## Class Diagrams

### Authentication and learner import implementation

```mermaid
classDiagram
  class AuthenticatedUser {
    <<dataclass>>
    UUID user_id
    str display_name
    str role
    datetime expires_at
  }
  class SessionSecurity {
    <<dataclass>>
  }
  class AuthModule {
    <<module>>
    authenticate_session(token, db) AuthenticatedUser
    get_current_user()
    require_coordinator(user)
  }
  class LearnersModule {
    <<module>>
    add_learner()
    update_learner()
    list_learners()
    find_learner_for_sign_in()
  }
  class CsvLearner {
    <<dataclass>>
    int row_number
    str first_name
    str family_name
  }
  class CsvDuplicate {
    <<dataclass>>
    int first_row_number
  }
  class CsvRowError {
    <<dataclass>>
    int row_number
    str field
    str message
  }
  class CsvParseResult {
    <<dataclass>>
    list records
    list duplicates
    list errors
  }
  AuthModule ..> AuthenticatedUser : returns
  AuthModule ..> SessionSecurity : cookie and origin configuration
  CsvParseResult "1" *-- "0..*" CsvLearner : records
  CsvParseResult "1" *-- "0..*" CsvDuplicate : duplicates
  CsvParseResult "1" *-- "0..*" CsvRowError : errors
  CsvDuplicate --> CsvLearner : record
  LearnersModule ..> AuthenticatedUser : actor identity supplied by route
```

### Local persistence model

These are SQLAlchemy `Table` objects, not ORM entity classes. Multiplicities describe local foreign-key relationships. `created_by` and `updated_by` are separate learner-to-user references.

```mermaid
classDiagram
  class users {
    <<table>>
    UUID id
    string username
    string password_hash
    string role
    bool is_active
    int failed_login_attempts
    datetime locked_until
  }
  class user_sessions {
    <<table>>
    UUID id
    UUID user_id
    string token_hash
    datetime expires_at
    datetime revoked_at
    datetime last_activity_at
  }
  class learners {
    <<table>>
    UUID id
    string first_name
    string family_name
    bool is_active
    UUID created_by
    UUID updated_by
  }
  class public_enquiries {
    <<table>>
    UUID id
    string name
    string contact
    string message
    string status
    datetime created_at
  }
  users "1" --> "0..*" user_sessions : user_id
  users "1" --> "0..*" learners : created_by
  users "0..1" --> "0..*" learners : updated_by
```

The database permits only one unrevoked session per user. An enquiry has no learner foreign key. Namesakes may be explicitly accepted during manual entry, so learner names are not unique database identifiers.
