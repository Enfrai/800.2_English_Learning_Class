# Ako UAT measurement evidence templates

Use one copy of these records for each UAT round. Use participant codes such as
`P01` instead of recording participant names. Keep one task row for every
participant and task attempt. Duplicate the task rows when more participants
take part. These records support section 6.3 of the Test Plan; they do not
replace the story results in section 7.3 or the sign-off in section 6.5.

## 1. Session and participant record

| Session ID | Date | Observer | Participant ID | Test role | Computer confidence (self-described) | Tasks assigned | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |

Include at least one participant who describes themself as less confident
using computers, as noted in the Test Plan. Do not record real learner data.

## 2. Required task observations: UA-01 to UA-10

Record each participant's actual attempt. `Completed alone` means no observer
prompt or help was needed. Enter actual elapsed time in minutes. Mark a task
that was not attempted as `No`; do not count it in the task-success denominator.

| Participant ID | UA | Role | Target (min) | Attempted (Y/N) | Completed alone (Y/N) | Success criteria met (Y/N) | Actual time (min) | Help or error observed | Notes / screenshot or evidence path |
| --- | --- | --- | ---: | --- | --- | --- | ---: | --- | --- |
| | UA-01 | Teacher | 1 | | | | | | |
| | UA-02 | Teacher | 3 | | | | | | |
| | UA-03 | Teacher | 1 | | | | | | |
| | UA-04 | Teacher | 4 | | | | | | |
| | UA-05 | Teacher | 2 | | | | | | |
| | UA-06 | Coordinator | 3 | | | | | | |
| | UA-07 | Coordinator | 3 | | | | | | |
| | UA-08 | Coordinator | 4 | | | | | | |
| | UA-09 | Coordinator | 3 | | | | | | |
| | UA-10 | Teacher | 1 | | | | | | |

Copy these ten rows for each additional participant. Keep participant order or
attempt sequence clear so repeated failures of the same UA task can be checked.
For the consecutive-failure check, count `Success criteria met = N` as a task
failure; `Completed alone` is recorded separately for the solo-completion rate.
The 6.3 success rate is:

`tasks completed alone ÷ tasks attempted × 100`.

For each attempted task, calculate `actual time ÷ target time`. The 6.3 time
measure is the median of these ratios. Record why if a target cannot be assessed.

### Optional tasks: UA-11 to UA-13

These later-story tasks may be recorded separately. Do not add them to the
UA-01 to UA-10 task-success percentage in section 6.3.

| Participant ID | UA | Role | Target (min) | Attempted (Y/N) | Completed alone (Y/N) | Success criteria met (Y/N) | Actual time (min) | Notes / evidence path |
| --- | --- | --- | ---: | --- | --- | --- | ---: | --- |
| | UA-11 | Visitor | 3 | | | | | |
| | UA-12 | Learner | 2 | | | | | |
| | UA-13 | Coordinator | 3 | | | | | |

## 3. Errors, confusion, and plain-language observation log

Log each observed issue once, with the task, what happened, and its evidence.
For plain language, use the same message/wording entry for every participant
who misunderstood it so the count of people misunderstanding the same item is
clear. Record triage and an owner for every issue.

| Observation ID | Date / session | Participant ID | UA | Type (error, confusion, wording) | Screen / step / exact wording | What happened | Participants who misunderstood this wording | Evidence path | Triaged? | Owner / disposition |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| | | | | | | | | | | |
| | | | | | | | | | | |
| | | | | | | | | | | |

If a session has no observed issues, record that explicitly rather than leaving
the log empty:

| Session ID | Date | Observer | Confirmation |
| --- | --- | --- | --- |
| | | | No errors, confusion, or misunderstood wording observed. |

For the 6.3 plain-language measure, count messages/words misunderstood by **two
or more participants**. The target is zero such messages.

## 4. SUS response and scoring record

Administer the adopted standard ten-item SUS questionnaire after the session.
Use its original item wording and 1–5 response scale; this template records
responses and scores but does not reproduce the questionnaire text.

| Participant ID | Date | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | SUS score / 100 | Completed form path |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |

Score each completed questionnaire by subtracting 1 from responses to odd items
(1, 3, 5, 7, 9), and subtracting even-item responses (2, 4, 6, 8, 10) from 5.
Add those adjusted values and multiply by 2.5 for that participant's SUS score.
The 6.3 result is the mean of the completed participant scores. Keep the
completed forms and calculation with the test evidence. The scoring method is
from [John Brooke's original SUS paper](https://hci-studies.org/methods-and-measures/downloads/SUS_Brooke1996.pdf).

## 5. Copy these results to Test Plan section 6.3

| Measure | Value to report | Evidence to reference |
| --- | --- | --- |
| Task success | Completed-alone attempts / attempted UA-01 to UA-10 tasks = ___ / ___ = ___%. Note any UA task failed by two consecutive participants. | Completed task observation records above. |
| Time | Median of actual-time / target-time ratios = ___×. | Completed task observation records above. |
| Errors and confusion | ___ items; all logged and triaged: ___. If none, state `0; no issues observed`. | Observation log above, including an explicit no-issues confirmation if applicable. |
| Satisfaction (SUS) | ___ participants; mean SUS score ___ / 100. | Completed SUS forms and score calculations above. |
| Plain language | ___ messages misunderstood by two or more participants. | Wording observations above. |
| Must-story acceptance | Use the 7.3 criteria totals and the 6.5 sign-off table. | Test Plan sections 7.3 and 6.5. |
