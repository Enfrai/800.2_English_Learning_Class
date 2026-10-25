# Ako Database Design

**Architecture:** Three microservices — User, Accessment, and Lesson  
**Database engine:** PostgreSQL  
**Design status:** Proposed technical design based on *Requirements Specification – Ako* (13 October 2026) and the agreed three-service architecture. Additional tables and rules are design recommendations, not confirmed source requirements.

## 1. Architecture and Conventions

| Microservice | Database | Responsibility |
|---|---|---|
| `user` | `user_db` | Authentication, user accounts, role-based access, learner records |
| `accessment` | `accessment_db` | Class sessions, attendance, corrections, optional QR check-in |
| `lesson` | `lesson_db` | Lesson library, tags, materials, Māori-content review |

Each service owns its database. Use UUID primary keys, `snake_case` identifiers, and `TIMESTAMPTZ` for timestamps. Cross-service IDs are references **without database foreign keys** and must be validated through service APIs. Foreign keys within the same database are permitted. Use UTC timestamps at the application/database boundary, displaying local time as appropriate.

The spelling `accessment` is retained to match the existing project; the service manages attendance rather than assessments or exams.

## 2. User Microservice (`user_db`)

### 2.1 `users` — Volunteer Accounts (US-001, US-002)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | User identifier |
| `username` | VARCHAR(100) | UNIQUE, NOT NULL | Login name |
| `password_hash` | VARCHAR(255) | NOT NULL | Secure password hash |
| `display_name` | VARCHAR(150) | NOT NULL | Display name |
| `email` | VARCHAR(255) | UNIQUE, NULL | Optional email |
| `role` | VARCHAR(20) | NOT NULL, CHECK | `coordinator` or `teacher` |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Whether login is allowed |
| `failed_login_attempts` | SMALLINT | NOT NULL, DEFAULT 0 | Consecutive failed attempts |
| `locked_until` | TIMESTAMPTZ | NULL | Login lock expiry |
| `last_login_at` | TIMESTAMPTZ | NULL | Last successful login |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Update timestamp |

**Rules:** Only coordinators manage teacher accounts. Lock an account for 10 minutes after five incorrect passwords. Retain inactive users for historical references. The first coordinator requires an initialization procedure (to be defined).

### 2.2 `user_sessions` — Authentication Sessions (Technical Support)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Session identifier |
| `user_id` | UUID | FK → `users.id`, NOT NULL | Signed-in user |
| `token_hash` | VARCHAR(255) | UNIQUE, NOT NULL | Hash of opaque session token |
| `created_at` | TIMESTAMPTZ | NOT NULL | Login timestamp |
| `last_activity_at` | TIMESTAMPTZ | NOT NULL | Last activity |
| `expires_at` | TIMESTAMPTZ | NOT NULL | Expiry timestamp |
| `revoked_at` | TIMESTAMPTZ | NULL | Revocation timestamp |

**Rules:** End sessions after 30 minutes of inactivity. As an existing project convention, a new login revokes previous active sessions for the same user; this single-session policy is not specified by the requirements document.

### 2.3 `learners` — Learner Records (US-003; US-017 later)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Learner identifier |
| `first_name` | VARCHAR(100) | NOT NULL | Learner first name |
| `family_name` | VARCHAR(100) | NOT NULL | Learner family name |
| `contact` | VARCHAR(255) | NULL | Optional contact information |
| `first_language` | VARCHAR(100) | NULL | Optional first language |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Active record flag |
| `created_by` | UUID | FK → `users.id`, NOT NULL | Creator |
| `updated_by` | UUID | FK → `users.id`, NULL | Last editor |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Update timestamp |

**Privacy:** Do not store birth dates, photos, addresses, ID numbers, or ethnicity. Names are not unique: different learners may have identical names. Duplicate detection and same-name QR sign-in are unresolved.

## 3. Accessment Microservice (`accessment_db`)

### 3.1 `class_sessions` — Dated Class Sessions (US-014)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Class session identifier |
| `session_date` | DATE | NOT NULL | Class date |
| `start_time` | TIME | NULL | Start time |
| `end_time` | TIME | NULL | End time |
| `status` | VARCHAR(20) | NOT NULL, CHECK | `scheduled`, `open`, or `closed` |
| `created_by` | UUID | NOT NULL; User-service reference | Creator's user ID |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Update timestamp |
| `closed_at` | TIMESTAMPTZ | NULL | Closure timestamp |

There is no separate `classes`, class-group, or timetable table. Session statuses are a proposed design choice.

### 3.2 `attendance_records` — Attendance (US-004, US-015)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Attendance identifier |
| `session_id` | UUID | FK → `class_sessions.id`, NOT NULL | Session |
| `learner_id` | UUID | NOT NULL; User-service reference | Learner |
| `status` | VARCHAR(20) | NOT NULL, CHECK | `present` or `absent` |
| `recorded_by` | UUID | NOT NULL; User-service reference | Initial recorder |
| `recorded_at` | TIMESTAMPTZ | NOT NULL | Initial recording time |
| `corrected_by` | UUID | NULL; User-service reference | Last correcting coordinator |
| `corrected_at` | TIMESTAMPTZ | NULL | Last correction time |

**Constraint:** `UNIQUE (session_id, learner_id)`. Only the coordinator may correct historical attendance. Whether an unticked learner automatically counts as absent must be confirmed.

### 3.3 `attendance_audits` — Correction History (Recommended)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Audit identifier |
| `attendance_id` | UUID | FK → `attendance_records.id`, NOT NULL | Corrected record |
| `old_status` | VARCHAR(20) | NOT NULL | Previous status |
| `new_status` | VARCHAR(20) | NOT NULL | Updated status |
| `corrected_by` | UUID | NOT NULL; User-service reference | Coordinator |
| `reason` | VARCHAR(500) | NULL | Optional explanation |
| `created_at` | TIMESTAMPTZ | NOT NULL | Correction timestamp |

This audit trail is a recommended implementation detail rather than an explicitly required table.

### 3.4 `checkin_windows` — QR Check-in (Later: US-011, US-012)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Check-in window identifier |
| `session_id` | UUID | FK → `class_sessions.id`, NOT NULL | Session |
| `token_hash` | VARCHAR(255) | UNIQUE, NOT NULL | Hash of QR token |
| `opened_by` | UUID | NOT NULL; User-service reference | Teacher/coordinator |
| `opened_at` | TIMESTAMPTZ | NOT NULL | Opening time |
| `expires_at` | TIMESTAMPTZ | NOT NULL | Expiry, at most four hours later |
| `closed_at` | TIMESTAMPTZ | NULL | Manual closing time |

A closed or expired code cannot record attendance. Rate limiting for repeated incorrect names should use short-lived server-side counters without retaining location or device fingerprints. The original specification proposes blocking more than ten incorrect names from one device within ten minutes for ten minutes; a privacy-preserving technical mechanism needs to be agreed.

### 3.5 `signin_failures` — Wrong Names at QR Sign-in (US-012)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Row identifier |
| `key_hash` | VARCHAR(64) | NOT NULL | HMAC-SHA256, keyed with `INTERNAL_API_KEY`, of the phone's random sign-in id or of its address; neither is stored |
| `failed_at` | TIMESTAMPTZ | NOT NULL | When a name that matched no learner was typed |

**Index:** (`key_hash`, `failed_at`). The sign-in page keeps a random id per phone, because phones on the library Wi-Fi share one address. Ten wrong names from one phone within ten minutes block that phone for ten minutes; fifty from one address block the address, so a changing id does not help. Without a valid id, ten from the address block it. Rows older than one hour are deleted on each new wrong name. A name shared by several learners is not counted. Self sign-ins are recorded in `attendance_records` with `recorded_by` set to the teacher who opened check-in (team decision, 25 Oct 2026), and store no location or device detail.

## 4. Lesson Microservice (`lesson_db`)

### 4.1 `lessons` — Lesson Library (US-006, US-007, US-008)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Lesson identifier |
| `title` | VARCHAR(255) | NOT NULL | Lesson title |
| `description` | TEXT | NULL | Lesson description/content |
| `lesson_date` | DATE | NOT NULL | Lesson date |
| `created_by` | UUID | NOT NULL; User-service reference | Creator |
| `source_lesson_id` | UUID | FK → `lessons.id`, NULL | Original lesson if copied |
| `has_maori_content` | BOOLEAN | NOT NULL, DEFAULT FALSE | Māori content flag |
| `review_status` | VARCHAR(20) | NOT NULL, CHECK, DEFAULT 'not_required' | `not_required`, `pending`, `reviewed`, `rejected` |
| `reviewed_by` | UUID | NULL; User-service reference | Coordinator who recorded the review |
| `reviewed_at` | TIMESTAMPTZ | NULL | When the review was recorded |
| `reviewer_name` | VARCHAR(150) | NULL | Reviewer's name as typed, e.g. a Kaiārahi outside the system (US-008) |
| `review_date` | DATE | NULL | Date of the review, not in the future (US-008) |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation time |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Update time |
| `deleted_at` | TIMESTAMPTZ | NULL | Soft deletion time |

**Rules:** Teachers edit their own lessons; coordinators may edit any lesson, pending team confirmation. Unreviewed Māori content must not be shown to learners; staff still see it (team decision, 23 Oct 2026). Only a coordinator records a review. Adding, replacing or removing a material of a reviewed lesson resets it to `pending` (US-008 AC4).

### 4.2 `tags` — Lesson Topics

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Tag identifier |
| `name` | VARCHAR(100) | UNIQUE, NOT NULL | Topic name |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation time |

### 4.3 `lesson_tags` — Lesson-to-Tag Mapping

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `lesson_id` | UUID | Composite PK; FK → `lessons.id` | Lesson |
| `tag_id` | UUID | Composite PK; FK → `tags.id` | Tag |

Primary key: `(lesson_id, tag_id)`.

### 4.4 `lesson_materials` — Attached Files (US-006; US-013 later)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Material identifier |
| `lesson_id` | UUID | FK → `lessons.id`, NOT NULL | Parent lesson |
| `file_name` | VARCHAR(255) | NOT NULL | Original filename |
| `storage_key` | VARCHAR(500) | NOT NULL | Relative path/object-storage key |
| `mime_type` | VARCHAR(100) | NOT NULL | MIME type |
| `file_size` | BIGINT | NOT NULL, CHECK >= 0 | File size in bytes |
| `uploaded_by` | UUID | NOT NULL; User-service reference | Uploader |
| `created_at` | TIMESTAMPTZ | NOT NULL | Upload time |
| `deleted_at` | TIMESTAMPTZ | NULL | Soft deletion time |

Store file content outside PostgreSQL, with metadata in this table. Supported types and maximum sizes need agreement.

### 4.5 `lesson_review_logs` — Māori Content Review History (Recommended)

| Column | PostgreSQL Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Review log identifier |
| `lesson_id` | UUID | FK → `lessons.id`, NOT NULL | Reviewed lesson |
| `review_status` | VARCHAR(20) | NOT NULL | Recorded decision |
| `reviewed_by` | UUID | NOT NULL; User-service reference | Reviewer |
| `comment` | TEXT | NULL | Review notes |
| `created_at` | TIMESTAMPTZ | NOT NULL | Review timestamp |

The `lessons` table holds current status; this table retains history.

## 5. Cross-Service References

| Source Table.Column | Owning Service | Target Entity | Validation |
|---|---|---|---|
| `class_sessions.created_by` | Accessment | User: `users.id` | User API |
| `attendance_records.learner_id` | Accessment | User: `learners.id` | User API |
| `attendance_records.recorded_by` | Accessment | User: `users.id` | User API |
| `attendance_records.corrected_by` | Accessment | User: `users.id` | User API |
| `lessons.created_by` | Lesson | User: `users.id` | User API |
| `lessons.reviewed_by` | Lesson | User: `users.id` | User API |
| `lesson_materials.uploaded_by` | Lesson | User: `users.id` | User API |

Additional audit and check-in actor fields follow the same rule. Service authentication and authorization are enforced at the API layer, not by client-provided role labels. Cross-service reference validation does not provide a distributed transaction; avoid hard deletion of referenced identities.

## 6. Indexes and Data Integrity

| Database | Table | Index / Constraint | Purpose |
|---|---|---|---|
| `user_db` | `users` | UNIQUE (`username`) | Prevent duplicate login names |
| `user_db` | `users` | INDEX (`role`, `is_active`) | Filter active volunteers |
| `user_db` | `user_sessions` | INDEX (`user_id`, `expires_at`) | Session retrieval and cleanup |
| `user_db` | `learners` | INDEX (`family_name`, `first_name`) | Name lookup |
| `accessment_db` | `class_sessions` | INDEX (`session_date`) | Date-range lookup |
| `accessment_db` | `attendance_records` | UNIQUE (`session_id`, `learner_id`) | One record per learner/session |
| `accessment_db` | `attendance_records` | INDEX (`learner_id`) | Attendance history |
| `accessment_db` | `attendance_audits` | INDEX (`attendance_id`, `created_at`) | Audit timeline |
| `lesson_db` | `lessons` | INDEX (`lesson_date`) | Date-based lookup |
| `lesson_db` | `lessons` | INDEX (`created_by`) | Teacher-owned lessons |
| `lesson_db` | `lesson_tags` | INDEX (`tag_id`) | Tag-based lookup |
| `lesson_db` | `lesson_materials` | INDEX (`lesson_id`) | Retrieve lesson attachments |

Also enforce enumerated statuses and roles using `CHECK` constraints. Add time-order checks where appropriate, e.g., session end after start and check-in expiry after opening.

## 7. Complete Table Inventory

| Service | Database | Table | Delivery |
|---|---|---|---|
| User | `user_db` | `users` | MVP |
| User | `user_db` | `user_sessions` | MVP technical support |
| User | `user_db` | `learners` | MVP |
| Accessment | `accessment_db` | `class_sessions` | MVP |
| Accessment | `accessment_db` | `attendance_records` | MVP |
| Accessment | `accessment_db` | `attendance_audits` | Recommended MVP |
| Accessment | `accessment_db` | `checkin_windows` | Later |
| Lesson | `lesson_db` | `lessons` | MVP |
| Lesson | `lesson_db` | `tags` | MVP |
| Lesson | `lesson_db` | `lesson_tags` | MVP |
| Lesson | `lesson_db` | `lesson_materials` | MVP |
| Lesson | `lesson_db` | `lesson_review_logs` | Recommended MVP |

**Total:** 3 databases, 12 proposed tables (11 for MVP, including recommended support/audit tables; 1 for later).

## 8. Deferred Public Page Data

The requirements include a public class-information page (US-009) and optional visitor enquiries (US-010), but the three-service design has no separate Public service. For this architecture, a small configuration entity within the User service is a possible solution; a `public_enquiries` table can be added later. **Neither table is included in the 12-table baseline**, and this service ownership needs confirmation.

Similarly, the requirements do not explicitly mandate a Lesson-to-ClassSession relationship. The initial schema keeps them independent. If materials must be exposed after check-in (US-013), a cross-service `lesson_id` reference on `class_sessions` may be introduced after agreeing on the association rules.

## 9. Open Design Decisions

| Decision | Why it matters |
|---|---|
| How is the initial coordinator created? | Bootstrap of authentication and administration |
| Does an unticked learner mean absent? | Attendance correctness and reporting |
| How are same-name learners distinguished? | Data quality and later QR check-in |
| Can multiple sessions occur on the same date? | Session uniqueness and workflow |
| Is a lesson linked to a class session? | Materials distribution and API integration |
| What are the permitted attachment formats and sizes? | Storage, validation and security |
| Does editing reviewed Māori content reset approval? | Cultural review and publication safety |
| Where does public-page configuration live? | Ownership of US-009/US-010 |
| How are QR name-attempt limits implemented without device tracking? | Security and privacy requirements |

## 10. Implementation Guidance

Use separate PostgreSQL databases and Alembic migration histories for the three FastAPI services. Keep SQLAlchemy models inside their owning services. Route APIs through the existing gateway, authenticate users centrally, and enforce resource-level permissions in the receiving service. Deploy with Docker Compose for a reproducible local setup. Prefer building and testing the MVP tables before implementing QR check-in or public enquiries.

**Source:** *Requirements Specification – Ako*, 13 October 2026, especially Sections 4–8. Detailed acceptance criteria are stated to be in the separate `MSE800_User_Stories_Oct19.docx` and were not available in this design pass.
