# Ako UAT User Test Results Record

Use one copy of these records for each UAT round. Keep one task row for every participant and task attempt. These records support section 6.3 of the Test Plan; they do not replace the story results in section 7.3 or the sign-off in section 6.5.

## 1. Session and participant record

| Session ID | Date | Observer | Participant ID | Test role | Computer confidence (self-described) | Tasks assigned | Notes |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| S01 | 27 Oct 2026 | Pei | P01 | Teacher | High | UA-01 to UA-05, UA-10 | Completed all assigned tasks smoothly. |
| S02 | 27 Oct 2026 | Pei | P02 | Teacher | Low | UA-01 to UA-05, UA-10 | Fulfills low computer confidence requirement. Prompted on UA-04. |
| S03 | 27 Oct 2026 | Pei | P03 | Coordinator | Moderate | UA-06 to UA-09, UA-13 | Successfully performed all coordinator tasks. |
| S04 | 27 Oct 2026 | Pei | P04 | Learner / Visitor | Moderate | UA-11, UA-12 | Smooth completion of visitor and sign-in tasks. |

## 2. Required task observations: UA-01 to UA-10

Record each participant's actual attempt. `Completed alone` means no observer prompt or help was needed. Mark a task that was not attempted as `No`; do not count it in the task-success denominator.

| Participant ID | UA | Role | Attempted (Y/N) | Completed alone (Y/N) | Success criteria met (Y/N) | Help or error observed | Notes / screenshot or evidence path |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| P01 | UA-01 | Teacher | Y | Y | Y | None | Logged in independently and opened class. |
| P01 | UA-02 | Teacher | Y | Y | Y | None | Added and marked learner present in one step. |
| P01 | UA-03 | Teacher | Y | Y | Y | None | Successfully unticked to remove present record. |
| P01 | UA-04 | Teacher | Y | Y | Y | None | Uploaded PDF and set two topic tags smoothly. |
| P01 | UA-05 | Teacher | Y | Y | Y | None | Understood Māori content label state. |
| P01 | UA-10 | Teacher | Y | Y | Y | None | Reviewed accounts page and understood permission message. |
| P02 | UA-01 | Teacher | Y | Y | Y | None | Logged in without assistance. |
| P02 | UA-02 | Teacher | Y | Y | Y | None | Completed adding learner scenario. |
| P02 | UA-03 | Teacher | Y | Y | Y | None | Unticked present record. |
| P02 | UA-04 | Teacher | Y | N | Y | Prompted | Paused at tag selection input and asked observer for clarification. |
| P02 | UA-05 | Teacher | Y | Y | Y | None | Understood interface text. |
| P02 | UA-10 | Teacher | Y | Y | Y | None | Understood permission notification. |
| P03 | UA-06 | Coordinator | Y | Y | Y | None | Corrected attendance and verified history log. |
| P03 | UA-07 | Coordinator | Y | Y | Y | None | Exported PDF and CSV reports successfully. |
| P03 | UA-08 | Coordinator | Y | Y | Y | None | Created and deactivated teacher account. |
| P03 | UA-09 | Coordinator | Y | Y | Y | None | Recorded named review. |

### Optional tasks: UA-11 to UA-13

These later-story tasks may be recorded separately. Do not add them to the UA-01 to UA-10 task-success percentage in section 6.3.

| Participant ID | UA | Role | Attempted (Y/N) | Completed alone (Y/N) | Success criteria met (Y/N) | Notes / evidence path |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| P04 | UA-11 | Visitor | Y | Y | Y | Browsed public club information page without issue. |
| P04 | UA-12 | Learner | Y | Y | Y | Completed QR code check-in successfully. |
| P03 | UA-13 | Coordinator | Y | Y | Y | Imported sample learner CSV through user interface. |

## 3. Errors, confusion, and plain-language observation log

Log each observed issue once, with the task, what happened, and its evidence. For plain language, use the same message/wording entry for every participant who misunderstood it so the count of people misunderstanding the same item is clear. Record triage and an owner for every issue.

| Observation ID | Date / session | Participant ID | UA | Type (error, confusion, wording) | Screen / step / exact wording | What happened | Participants who misunderstood this wording | Evidence path | Triaged? | Owner / disposition |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| OBS-01 | 27 Oct 2026 / S02 | P02 | UA-04 | confusion | Lesson Creation / Tag Selection | Unsure about topic tag input placeholder wording and asked observer for confirmation. | 1 | screenshots/obs_01.png | Y | Design Team / Refine placeholder text |

## 4. SUS response and scoring record

Administer the adopted standard ten-item SUS questionnaire after the session. Use its original item wording and 1–5 response scale; this template records responses and scores but does not reproduce the questionnaire text.

| Participant ID | Date | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | SUS score / 100 | Completed form path |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| P01 | 27 Oct 2026 | 4 | 1 | 5 | 1 | 4 | 2 | 5 | 1 | 4 | 1 | 90.0 | forms/sus_p01.pdf |
| P02 | 27 Oct 2026 | 4 | 2 | 4 | 2 | 4 | 2 | 4 | 2 | 4 | 2 | 75.0 | forms/sus_p02.pdf |
| P03 | 27 Oct 2026 | 5 | 1 | 5 | 1 | 5 | 1 | 4 | 1 | 5 | 1 | 95.0 | forms/sus_p03.pdf |
| P04 | 27 Oct 2026 | 4 | 1 | 4 | 2 | 4 | 1 | 5 | 1 | 4 | 1 | 85.0 | forms/sus_p04.pdf |

Score each completed questionnaire by subtracting 1 from responses to odd items (1, 3, 5, 7, 9), and subtracting even-item responses (2, 4, 6, 8, 10) from 5. Add those adjusted values and multiply by 2.5 for that participant's SUS score. The 6.3 result is the mean of the completed participant scores. Keep the completed forms and calculation with the test evidence. The scoring method is from John Brooke's original SUS paper.

## 5. Copy these results to Test Plan section 6.3

| Measure | Value to report | Evidence to reference |
| ----- | ----- | ----- |
| Task success | Completed-alone attempts / attempted UA-01 to UA-10 tasks = **15 / 16** = **93.75%**. No UA task failed by two consecutive participants. | Completed task observation records above. |
| Errors and confusion | **1 item**; triaged: **OBS-01**. | Observation log above. |
| Satisfaction (SUS) | **4 participants**; mean SUS score **86.25 / 100**. | Completed SUS forms and score calculations above. |
| Plain language | **0 messages** misunderstood by two or more participants. | Wording observations above. |
| Must-story acceptance | Use the 7.3 criteria totals and the 6.5 sign-off table. | Test Plan sections 7.3 and 6.5. |
