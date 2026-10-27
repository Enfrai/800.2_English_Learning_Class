# Lesson Service UML

Source baseline: `feature/v1.0/pre_release`, commit `f5e63dd0ccacffa4f8f0d6d920b04a94d51302a4`.

Diagrams describe the implemented application, not every possible requirement. GitHub renders the Mermaid fences directly. Use cases use a Mermaid flowchart with actor nodes, oval use cases and a system boundary because Mermaid has no native UML use-case syntax. Activity diagrams use decisions and explicit outcomes. Class diagrams distinguish actual classes from `table`, `module`, `type` and `component` representations. Only selected fields and operations are shown; function-based modules are not implemented service classes. Dashed dependencies represent calls or logical references, not database foreign keys.

## Scope and source map

Source paths in this document are relative to [server/services/lesson](../../../server/services/lesson).

This service owns the lesson library, tags, uploaded files, copying and Māori content review metadata. It authenticates staff through User Service. Accessment Service supplies learner authorization and calls the internal shared-material routes.

| Area | Source |
| --- | --- |
| Lesson CRUD, search, tags and materials | `lesson_api.py` |
| Copying lessons and selected files | `lesson_copy.py` |
| Review rules and endpoints | `maori_review.py`, `maori_review_api.py` |
| Learner-visible material list and download | `shared_materials.py` |
| Staff identity and persistence | `user_client.py`, `models.py`, `schema.py` |

## Use Case Diagram

```mermaid
flowchart TB
  staff["Actor: Teacher or Coordinator"]
  editor["Actor: Lesson author or Coordinator"]
  coord["Actor: Coordinator"]
  access["Actor: Accessment Service"]
  subgraph lesson["Lesson Service"]
    browse(["Browse, search and filter lessons and tags"])
    create(["Create lesson or copy existing lesson"])
    download(["Read lessons and download staff materials"])
    edit(["Edit or delete lesson and manage material sharing"])
    files(["Upload or remove lesson materials"])
    flag(["Flag or unflag Māori content"])
    review(["Record review name and date"])
    status(["Read review status"])
    shared(["List and download eligible shared materials"])
  end
  staff --- browse
  staff --- create
  staff --- download
  staff --- status
  editor --- edit
  editor --- files
  editor --- flag
  coord --- review
  access --- shared
```

Teacher edits require lesson ownership; Coordinators may edit other authors' lessons. Copying creates a new lesson owned by the copying staff member. Review recording captures the supplied reviewer name and date; the system does not itself perform cultural review or verify the reviewer's qualifications. Internal material endpoints require the internal API key.

## Activity Diagrams

### Create, copy or edit a lesson

```mermaid
flowchart TD
  start(["Staff request"]) --> auth["Verify staff session with User Service"]
  auth --> action{"Action?"}
  action -->|Create| validate["Validate title, date and tags"]
  action -->|Copy| source["Find live source lesson and selected materials"]
  source --> validate
  action -->|Edit or delete| own{"Author or Coordinator?"}
  own -->|No| deny["403"]
  own -->|Yes| operation{"Delete?"}
  operation -->|No| validate
  validate --> valid{"Valid input and available source?"}
  valid -->|No| error["Return field, missing-source or file error"]
  valid -->|Yes| copying{"Copy requested?"}
  copying -->|No| save["Save lesson fields and tags in transaction"]
  copying -->|Yes| copy["Insert new owned lesson and copy selected files to new storage keys"]
  copy --> success{"All copies and writes succeed?"}
  success -->|No| clean["Roll back and remove new copied files"]
  success -->|Yes| done(["Commit and return new lesson"])
  save --> done
  operation -->|Yes| tombstone["Soft-delete lesson and its materials in transaction"]
  tombstone --> purge["Commit and attempt to purge stored files"]
  purge --> deleted(["Return 204 and retain lesson tombstone"])
```

The source lesson is retained after a copy. `source_lesson_id` records provenance. A missing or deleted source is rejected. Soft-deleted lesson IDs may still be referenced by Accessment Service; reads and downloads check availability.

### Upload and review visibility

```mermaid
flowchart TD
  start(["Upload material"]) --> permission{"Live lesson and permitted editor?"}
  permission -->|No| deny["Reject request"]
  permission -->|Yes| validate["Validate file size, extension and content signature"]
  validate --> valid{"PDF, DOCX, JPG or PNG and at most 10 MiB?"}
  valid -->|No| invalid["Return validation error"]
  valid -->|Yes| write["Write generated storage key and insert material metadata"]
  write --> flagged{"Lesson has Māori content?"}
  flagged -->|Yes| reset["Reset review after material change and log transition as required"]
  flagged -->|No| commit["Commit upload"]
  reset --> commit
  commit --> next{"Coordinator records review?"}
  next -->|Yes| fields["Validate flagged lesson, reviewer name and review date"]
  fields --> record["Set reviewed metadata and append review log"]
  record --> visible(["Eligible shared files may be visible to learners"])
  next -->|No| waiting(["Flagged unreviewed material remains hidden from learners"])
```

Upload failures roll back database writes and remove the new file. The review rule is also re-evaluated after material deletion. Unflagged lessons do not require review; flagged lessons require `reviewed` status for learner visibility. Sharing a file and recording a review are separate operations.

### Learner shared material request

```mermaid
flowchart TD
  start(["Internal shared-material request from Accessment"]) --> key{"Valid internal key?"}
  key -->|No| deny["403"]
  key -->|Yes| lesson{"Live lesson exists?"}
  lesson -->|No| missing["404"]
  lesson -->|Yes| review{"Unflagged or reviewed?"}
  review -->|No listing| empty["Return pending message and no files"]
  review -->|No download| missing
  review -->|Yes| operation{"List or download?"}
  operation -->|List| list["Return nondeleted files with share flag enabled"]
  operation -->|Download| file{"File belongs to lesson, shared, live and safely stored?"}
  file -->|No| missing
  file -->|Yes| download["Return file with attachment and no-store headers"]
```

This service does not accept a learner cookie as authorization. Accessment validates the learner grant and determines the associated lesson before calling these endpoints.

## Class Diagrams

### Routes and review implementation

```mermaid
classDiagram
  class Staff {
    <<dataclass>>
    UUID id
    str display_name
    str role
    bool is_coordinator
  }
  class LessonIn {
    <<Pydantic>>
    str title
    date lesson_date
    str description
    list tags
  }
  class CopyIn {
    <<Pydantic>>
    list material_ids
  }
  class ReviewIn {
    <<Pydantic>>
    str reviewer_name
    date review_date
  }
  class ReviewOut {
    <<Pydantic>>
    UUID lesson_id
    str review_status
    bool visible_to_learners
  }
  class LessonApi {
    <<module>>
    create_lesson_router()
    validate_lesson()
    find_lesson()
    read_file()
  }
  class MaoriReview {
    <<module>>
    set_maori_content()
    record_review()
    reset_review_after_material_change()
    visible_to_learners()
  }
  CopyIn --|> LessonIn
  LessonApi ..> LessonIn : validates
  LessonApi ..> Staff : authorizes
  LessonApi ..> MaoriReview : resets on material changes
  MaoriReview ..> ReviewOut : mapped by review API
  MaoriReview ..> ReviewIn : values supplied by review API
```

### Local persistence model

```mermaid
classDiagram
  class lessons {
    <<table>>
    UUID id
    str title
    date lesson_date
    UUID created_by
    UUID source_lesson_id
    bool has_maori_content
    str review_status
    str reviewer_name
    date review_date
    datetime deleted_at
  }
  class tags {
    <<table>>
    UUID id
    str name
  }
  class lesson_tags {
    <<table>>
    UUID lesson_id
    UUID tag_id
  }
  class lesson_materials {
    <<table>>
    UUID id
    UUID lesson_id
    str storage_key
    str file_name
    str mime_type
    int file_size
    bool share_with_learners
    datetime deleted_at
  }
  class lesson_review_logs {
    <<table>>
    UUID id
    UUID lesson_id
    str review_status
    UUID reviewed_by
    str comment
    datetime created_at
  }
  lessons "0..1" --> "0..*" lessons : source_lesson_id
  lessons "1" --> "0..*" lesson_tags : lesson_id
  tags "1" --> "0..*" lesson_tags : tag_id
  lessons "1" --> "0..*" lesson_materials : lesson_id
  lessons "1" --> "0..*" lesson_review_logs : lesson_id
```

These boxes represent SQLAlchemy tables. `created_by`, `uploaded_by` and reviewer IDs refer logically to User Service users; there are no cross-database foreign keys. Material bytes live in the configured filesystem, while metadata lives in the database. Database status constraints include `rejected`; no rejection action is exposed by `ReviewIn` in this branch.
