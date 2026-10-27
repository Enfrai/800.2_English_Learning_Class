# Ako User Manual

Version 1.2 | 27 October 2026 | English

Ako supports one English conversation club. This manual explains how visitors,
learners, teachers and coordinators use its pages. Follow the role and menu path
at the start of each task. The instructions describe the current release,
including limits that affect normal operation.

Installation and environment configuration are in the [project README](../../README.md).
A Word copy is available as [Ako User Manual](Ako_User_Manual.docx).

## Contents

1. [Getting started and permissions](#1-getting-started-and-permissions)
2. [Public information and enquiries](#2-public-information-and-enquiries)
3. [Staff login and account administration](#3-staff-login-and-account-administration)
4. [Learner records and CSV import](#4-learner-records-and-csv-import)
5. [Class sessions and lesson selection](#5-class-sessions-and-lesson-selection)
6. [Attendance and follow-up](#6-attendance-and-follow-up)
7. [QR check-in and learner materials](#7-qr-check-in-and-learner-materials)
8. [Lesson library and cultural review](#8-lesson-library-and-cultural-review)
9. [A complete class workflow](#9-a-complete-class-workflow)
10. [Troubleshooting and current limitations](#10-troubleshooting-and-current-limitations)
11. [Feature coverage](#11-feature-coverage)
12. [Send feedback](#12-send-feedback)

## 1 Getting started and permissions

### 1.1 Open Ako

1. Ask the person running Ako for its web address.
2. On the host computer, the usual local address is http://localhost:8080.
3. Open the address in a current browser. Allow cookies and downloads.
4. Choose a link in the public navigation, or sign in as staff.

A phone must use a reachable computer or hosted address supplied by the teacher.
The phone's own localhost address cannot reach the teacher's computer.

Public information, the enquiry form and staff login are separate pages. Opening
a navigation link changes the page; it does not expand a section of the login form.

### 1.2 Roles and available actions

| Role | Account | Available work |
| --- | --- | --- |
| Visitor | None | Read class information and send an enquiry |
| Learner | None | Scan an open class QR code, sign in by name and download shared materials |
| Teacher | Staff login | Manage learners and classes, take today's attendance, view past attendance/history, create and reuse lessons, edit own lessons |
| Coordinator | Staff login | Teacher functions, manage staff, import learners, correct past attendance, export reports, view enquiries, record cultural reviews and edit any lesson |

Learners are records, not login accounts. Sending an enquiry does not add a learner
or enrol someone. There are no advance enrolments, class groups or learner timetables.

### 1.3 Staff navigation

After login, use **Home**, **Class sessions**, **Learners** and **Lessons**.
Coordinators also see **Attendance reports**, **Enquiries** and **Account management**.
Use **Log out** when finished, especially on a shared computer.

### 1.4 Safe use

- Check the class date and learner identity before changing attendance.
- Use **Cancel** when a confirmation is not intended.
- Wait for a save result; avoid repeatedly clicking a write button.
- If a response is lost, refresh and inspect the record before trying again.
- Keep learner details private. Do not include passwords or personal records in screenshots sent for support.
- Use made-up learner data for demonstrations and tests.

## 2 Public information and enquiries

### 2.1 Read class information

**Role:** Anyone. **Entry:** **Class Information**, at /class-information.

1. Open **Class Information** in the public navigation.
2. Read the class day, time, venue and contact section.
3. If the page says the details are samples, confirm them before travelling.
4. Use the approved phone/email link, when present, or **Send an enquiry**.
5. Choose **Staff Login** only if you have a staff account.

The current default address and schedule are labelled sample information.
Publishing approved replacements is a maintainer configuration task; there is
no public-page editing screen.

### 2.2 Ask about classes

**Role:** Visitor. **Entry:** **Ask About Classes**, at /ask-about-classes.

1. Open **Ask About Classes**.
2. Enter your name.
3. Choose Email or Phone and enter a valid contact.
4. Optionally enter a message of up to 500 characters.
5. Read and tick the consent checkbox.
6. Choose **Send enquiry** and wait for the thank-you message.

Correct any field error and submit again. Consent and a valid contact are required.
If the request fails without a clear result, avoid sending repeated copies.
An enquiry is a request for contact; it is not attendance or registration.

### 2.3 View received enquiries

**Role:** Coordinator. **Entry:** **Enquiries**, at /enquiries.

1. Log in as a coordinator.
2. Choose **Enquiries**.
3. Read the visitor's name, contact details, message and submission time.
4. Use **Next** or **Previous** to browse pages.
5. Use **Refresh** to return to the newest page.
6. Contact the visitor outside Ako using the supplied details.

Teachers cannot open this list. There is no enquiry status editor, assignment,
delete action or built-in email sending. If the visitor joins, add their learner
record separately after confirming the necessary details.

## 3 Staff login and account administration

### 3.1 Log in

**Role:** Teacher or Coordinator. **Entry:** **Staff Login**, at /.

1. Obtain your username and password from the coordinator or maintainer.
2. Open the login page.
3. Enter your username and password, then submit the login form.
4. Confirm that your role's home page opens.
5. Use the staff menu for the required function.

An unchanged local demo has username demo and password DemoPass123!.
Use the configured credentials if the maintainer changed them.
Do not share the coordinator account for everyday teacher work.

A wrong password shows **Username or password is incorrect**. After five
consecutive failures the account is locked for ten minutes; wait for the
displayed retry time. An inactive account cannot log in.

### 3.2 Log out and session expiry

1. Save any work in progress.
2. Choose **Log out** in the staff header.
3. Confirm that the login page appears.

A session ends after 30 minutes without user activity. Background refreshes are
not activity. Sign in again if redirected; unsaved form data may need re-entering.
A new login for the same account ends its previous session, so use separate accounts.

### 3.3 Create a teacher account

**Role:** Coordinator. **Entry:** **Account management**, at /account-management.

1. Under **Add Teacher**, enter the staff member's name.
2. Enter a unique username.
3. Enter a temporary password with at least eight characters.
4. Choose **Create Teacher**.
5. Confirm the new entry is Active in **Teacher accounts**.
6. Give the credentials to that teacher through a private channel.

A duplicate username shows **Username already taken**. A short password shows
**Password must be at least 8 characters**. The page does not create learner or
coordinator accounts. No self-service password change/reset page is provided.

### 3.4 Edit a teacher name

1. Find the teacher in **Teacher accounts**.
2. Choose **Edit name**.
3. Change the name under **Edit Teacher name**.
4. Choose **Save name**, or **Cancel edit**.
5. Verify the new display name in the list.

This operation changes the display name, not the username, password or role.

### 3.5 Deactivate an account

1. Check the account's name and username.
2. Choose **Deactivate** beside an active account.
3. Read the confirmation.
4. Choose **Confirm deactivation**, or **Cancel deactivation**.
5. Verify the Inactive state.

The account cannot log in after deactivation. Its past lessons and attendance
remain stored. Accounts are not deleted. The coordinator list also provides
deactivation, but the last active coordinator cannot be deactivated.
There is no reactivation button or general coordinator creation page.

If a teacher forgets a password or an account must be restored, ask the maintainer.
Do not delete databases as a password recovery method.

## 4 Learner records and CSV import

### 4.1 Add a learner

**Role:** Teacher or Coordinator. **Entry:** **Learners**, at /learners.

1. Choose **Add learner**.
2. Enter **First name** and **Family name**.
3. Optionally enter **First language** and **Phone or email**.
4. Save the form and check the learner appears in the list.
5. If a duplicate-name warning appears, compare the people carefully.
6. Choose **Cancel** for an existing person, or **Add anyway** for a different
   person who genuinely shares that name.

Both names are required and each allows up to 100 characters.
Keep macrons and other spelling as the learner supplies them.
Do not record birth dates, home addresses or identity numbers.

### 4.2 Update a learner

1. Find the learner on **Learners**.
2. Choose **Edit** for the correct record.
3. Update the name, first language or contact.
4. Save, then check the list.
5. Choose **Cancel** instead if no change is needed.

The page does not provide learner deletion or a learner login.
For same-name people, verify contact/language information before editing.

### 4.3 Import a CSV file

**Role:** Coordinator. **Entry:** **Learners** > **Import CSV**.

1. Choose **Import CSV** to open the panel.
2. Choose **Download CSV template**.
3. Keep the header exactly as supplied, in this order:

```csv
first_name,family_name,first_language,contact
Ana,Example,Spanish,ana@example.test
Tāne,Sample,Te reo Māori,
```

4. Enter one made-up learner per row for a demo. Use proper CSV quoting for commas.
5. Save as UTF-8 CSV with a .csv extension, no larger than 1 MiB (1,048,576 bytes).
6. Select **CSV file**, then choose **Import learners**.
7. Check the imported count and refreshed learner list.
8. Review **Skipped duplicate learners** and **Rejected rows**, including row numbers.
9. Correct rejected rows and import a corrected file only after checking what already saved.

Header row is row 1. First language and contact can be empty; both name fields are
required. Duplicate names in the file or database are skipped and reported, so CSV
import is not the way to create an intentional same-name learner. Use **Add learner**
and **Add anyway** instead.

Bad encoding, header, CSV structure, file type or file size rejects the file.
Individual invalid learner rows are reported while other valid rows can import.
Import does not update existing records. A lost response does not prove nothing
was imported: inspect the list before retrying.

## 5 Class sessions and lesson selection

### 5.1 Start or reopen today's class

**Role:** Teacher or Coordinator. **Entry:** **Class sessions**, at /sessions.

1. Choose **Start today's class**.
2. Check the displayed class date.
3. If today's session already exists, the same session opens.
4. Use **Attendance** to take the register, or select a lesson first.

There is one session per date. The club date uses Pacific/Auckland by default,
which may differ from another device's local date.

### 5.2 Create or open a past class

1. On **Class sessions**, choose **New class session**.
2. Select today or an earlier **Class date**.
3. Choose **Create or open class**.
4. An existing date opens its session; a new date creates one.

A future date is refused with **Date cannot be in the future**.
The list is newest first and shows lesson information and present counts.
A teacher can view past attendance; a coordinator makes corrections.

### 5.3 Link or change a lesson

1. Open a class using **Open class** or its date.
2. Under **Class lesson**, choose a saved lesson.
3. Choose **Save lesson**.
4. Check the lesson title shown on the class page.
5. To unlink, choose **No lesson linked** and save.

Linking does not change the lesson's content or date.
One lesson can be reused for different sessions.
Learner materials follow the class's current linked lesson, so check sharing
and cultural review before learners sign in. Changing the link later changes
what valid material access for that class resolves to.

### 5.4 Delete an empty session

1. Open the session and check the date.
2. Choose **Delete session**.
3. Read the warning, then choose **Confirm deletion** or **Cancel deletion**.

Any attendance record prevents deletion, including a recorded absence.
The message is **This session has attendance and cannot be deleted**.
Deleting an eligible empty session does not delete its lesson.

### 5.5 Finish teaching

Close QR check-in when sign-in ends and log out when staff work is finished.
There is currently no separate **End class** button. Closing QR check-in only
stops new QR sign-ins; it does not end existing material access or mark the
class as closed for history purposes.

## 6 Attendance and follow-up

### 6.1 Mark attendance by hand

**Role:** Teacher or Coordinator. **Entry:** **Class sessions** > today's class > **Attendance**.

1. Confirm the date and the learner's identity.
2. Tick the learner's checkbox.
3. Check **Present**, the recorded time and the updated present count.
4. To undo a mistake during today's class, untick the checkbox.
5. Check that the present count falls.

Repeated marking does not create a duplicate and can show **Already signed in**.
The attendance page refreshes approximately every three seconds to pick up QR
sign-ins. If live refresh fails, check the warning and wait or reload.

A person does not need a phone: staff can record attendance manually.

### 6.2 Add an unexpected learner and mark present

1. First check whether the learner already appears in the list.
2. For a genuinely new name, use **Learner not on the list**.
3. Enter First name and Family name.
4. Choose **Add and mark present**.
5. Check that the learner appears, is marked present and the count increases.

For an existing name, this shortcut reuses an existing learner.
If several learners share a name, it currently chooses the earliest-created
record. Do not use this shortcut for same-name people. Add an intentional
duplicate on **Learners**, then tick the correct record on Attendance.

If adding succeeds but attendance fails, reload both pages and check before retrying.

### 6.3 Print today's list

1. Open **Attendance** for the required session.
2. Choose **Print this list**.
3. In the browser print dialog, choose A4 and inspect the preview.
4. Select a printer, or save using the browser's PDF option.

This prints the visible session list. For a date-range report, a coordinator uses
**Attendance reports** instead.

### 6.4 Correct past attendance

**Role:** Coordinator. **Entry:** **Class sessions** > past class > **Attendance**.

1. Open the correct past class.
2. Confirm the notice that every correction is logged.
3. Tick the correct learner to mark Present, or untick to change to Absent.
4. Check the updated count.
5. Read **Change history** below the register.

History shows who changed attendance, what changed and when.
Unticking a past record keeps an Absent record for audit purposes.
There is no correction-reason field on the page.
Teachers see past attendance read-only with **Only a coordinator can correct past attendance**.

### 6.5 View a learner's history

**Role:** Teacher or Coordinator. **Entry:** **Learners** > the learner's **History** link.

1. Check the learner name at the top.
2. Review sessions newest first and their Present/Absent values.
3. Read the **Present X of Y** summary.
4. Optionally set Start date, End date or both, then choose **Apply dates**.
5. Choose **Reset dates** to remove filters.

Dates are inclusive; either date can be blank for an open-ended range.
A reversed range is refused. A learner with no recorded history shows
**No attendance recorded yet**. History is read-only for both roles;
coordinators correct through the relevant session's attendance page.

Today's unfinished session is normally excluded until the next day. For current
attendance, use the session register. History excludes unrecorded sessions before
the learner record's creation, while exports use all selected class dates.
Treat these as different scopes until their reporting rules are aligned.

### 6.6 Download attendance reports

**Role:** Coordinator. **Entry:** **Attendance reports**, at /reports/attendance.

1. Enter Start date and End date. Both are required and included.
2. On supported browsers, click the date area or calendar icon to open the picker;
   keyboard/native date entry remains available.
3. Choose **Download PDF** or **Download CSV**.
4. Check the browser's Downloads location.
5. Open and verify the date range and learner names.

PDF uses A4 landscape pages suitable for black-and-white printing.
CSV has one row per learner and one column per actual class date.
Current learners and people with attendance in the range are included.
A missing Present record is exported as Absent, including dates before some
learners were first entered. Reports reflect the latest corrections.

If no class falls in the range, **No classes found for these dates** appears and
no file downloads. Start after End is refused with **Start date must be before end date**.
Teachers cannot view or export these reports.

## 7 QR check-in and learner materials

### 7.1 Prepare shared materials

**Role:** Lesson author or Coordinator.

1. Create or open the lesson in **Lessons**.
2. Add the files needed by learners.
3. Tick **Share [file name] with learners** for each intended file.
4. If it contains Māori content, ask the coordinator to record the review.
5. Open today's class and link that lesson.

Files are private to staff by default. Shared files on an unreviewed Māori lesson
remain hidden from learners. Staff can still see that lesson.

### 7.2 Open and display QR check-in

**Role:** Teacher or Coordinator. **Entry:** today's class > **QR check-in**.

1. Ensure the phone can reach the address configured by the maintainer.
2. Choose **Open check-in**.
3. Check the date, sign-in link and expiry.
4. Display the code, or choose **Print QR code**.
5. Inspect the A4 print preview and print the black-and-white code.
6. Open **Attendance** to watch sign-ins.

Only today's eligible class can open check-in. A code is session-specific and
expires after at most four hours, or at club midnight if earlier.
If the print dialog does not open, retry from the class page using a desktop browser.
The printed code is at least 8 cm wide.

### 7.3 Sign in as a learner

**Role:** Learner. **Entry:** scan the teacher's displayed QR code.

1. Scan with the phone camera and open the link in the browser.
2. Check the class date.
3. Enter First name and Family name.
4. Choose **Sign in** once.
5. Wait for **You are signed in**.
6. Read the materials displayed below, or choose **Lesson materials**.

No account, password or app is needed. The full learner list is never shown.
Case differences and Māori macron variations are supported by name matching.
For a name not found, or shared by several learners, ask the teacher.
The teacher must identify and tick the correct learner rather than guessing.

**Already signed in** means no second attendance was created. It does not
necessarily grant material access if staff marked you manually or your browser
lost its earlier material cookie. Ask the teacher for the handout in that case;
unticking and re-ticking attendance is not a documented recovery procedure.

### 7.4 Close or reopen QR check-in

1. On the class page choose **Close check-in**.
2. Confirm the closed state and removal of the active code.
3. New scans can no longer record attendance.
4. If sign-in must resume today, choose **Open check-in** again.
5. Use the currently displayed code.

A closed or expired link shows **Check-in is closed. Please ask the teacher**.
Closing check-in does not revoke already granted material access.

### 7.5 Download and return to materials

**Role:** Learner with successful QR sign-in. **Entry:** **Lesson materials**, at /materials.

1. On the same browser used for successful sign-in, open **Lesson materials**.
2. Choose **Download** beside a file.
3. Open it from the phone/browser Downloads area.
4. Return to /materials on that same origin and browser within 24 hours.

Files download with their original names. Only selected shared files appear.
A class with no linked lesson shows **No materials for today**.
Unreviewed Māori content shows **Materials will be added soon**; attendance remains recorded.

Access expires 24 hours after successful sign-in and is not extended by viewing.
Private browsing, cookie deletion, another phone, or switching hostname can lose access.
After expiry, follow the request to scan a current class code again.
If no class is open, ask staff for the material.

### 7.6 Wrong-name attempts

Ten wrong names within ten minutes block that phone for ten minutes.
A higher shared-address limit of fifty protects the service.
If **Too many tries. Please ask the teacher** appears, stop retrying and ask staff.
Learners without phones continue to use manual attendance.

### 7.7 Verify QR sign-in step by step

Use this walkthrough to check US-011, US-012 and US-013 together on a real phone.
Use a disposable demonstration dataset and a new, uniquely named test learner.
These instructions are a test procedure, not a record that the checks passed.

**Step 1 Start the system**

Start Docker Desktop or the Docker daemon. In the repository root, enter server.
If server/.env does not exist, copy .env.example to .env before starting.
Keep existing configuration and data volumes.

```sh
cd server
docker compose up -d --build
docker compose ps
```

Open http://localhost:8080 on the computer. Wait for the services to become ready.
For an unchanged local demonstration, the coordinator is demo / DemoPass123!.
Otherwise use the configured account.

**Step 2 Make the address reachable from the phone**

Connect the computer and phone to the same reachable Wi-Fi network.
Find the computer's LAN IPv4 address in its active network settings.
Replace 192.168.1.20 below with that actual address. Edit server/.env:

```dotenv
AKO_BIND_ADDRESS=0.0.0.0
CHECKIN_PUBLIC_ORIGIN=http://192.168.1.20:8080
COOKIE_SECURE=false
```

This is an HTTP LAN demonstration configuration. Keep private INTERNAL_API_KEY
and CHECKIN_TOKEN_SECRET values configured consistently through Compose.
Do not overwrite existing database passwords or remove volumes.

From server, apply the settings:

```sh
docker compose up -d --build
docker compose restart nginx
```

On the phone, open http://192.168.1.20:8080/class-information.
Continue only when it loads. If it fails, check the IP, inbound TCP 8080 firewall
rule and Wi-Fi client isolation. A guest network can block communication.
The QR link must use the reachable IP, not localhost or 0.0.0.0.
Use HTTPS and the corresponding secure-cookie configuration for an HTTPS deployment.

**Step 3 Add a test learner**

On the computer, log in and open Learners. Choose Add learner.
Create First name Ana and Family name QRTest, or another unique test name.
Check the list for an existing record before saving.
Do not manually tick this learner Present: QR sign-in must create the first attendance.

**Step 4 Prepare a shared test file**

Open Lessons > New lesson. Enter a title, date and topic tag.
Upload a small PDF and tick its Share with learners checkbox.
For this basic check, leave Contains Māori content unticked.
Choose Save lesson and confirm that the file is listed.
Use a different lesson for cultural-review tests.

**Step 5 Open today's class and QR window**

Choose Class sessions > Start today's class.
Check the date. Select the test lesson under Class lesson and choose Save lesson.
Under QR check-in, choose Open check-in.
Check that the code, sign-in link and expiry appear.
The link must start with the LAN origin configured in Step 2.
If today's session already has attendees, note the starting count instead of assuming zero.
Keep the generated sign-in link available for the closure test.

**Step 6 Scan and sign in**

Scan the displayed code with the phone camera.
Open the link in the browser, check today's date and enter Ana / QRTest.
Choose Sign in once. Expect You are signed in and the lesson materials area.
No staff login, learner password or app should be required.

**Step 7 Confirm attendance on the computer**

Open Attendance for that same class and find Ana QRTest.
Allow approximately three seconds for automatic refresh.
Expect Present, a recorded time and a count increase of one.
It must appear within the ten-second acceptance window without manually ticking it.
Confirm the learner is not recorded twice.

**Step 8 Download and revisit the materials**

On the phone, choose Lesson materials and Download beside the test PDF.
Verify the original filename and that the file opens.
Return to /materials on the same origin and browser; the shared file should remain available.
Do not switch between the LAN IP and localhost, clear cookies, or use a new private window.
Those actions do not preserve the material-access cookie.

**Step 9 Check duplicate sign-in and closure**

Reopen the original sign-in link and enter the same name.
Expect Already signed in and no increase in attendance.
Then choose Close check-in on the computer and reload the saved sign-in link.
Expect Check-in is closed. Please ask the teacher, with no new attendance.
Finally reopen /materials in the already authorized phone browser.
Closing check-in should not revoke its existing 24-hour material access.

### 7.8 Additional validation cases and results

Run each case with suitable fresh test learners and note the starting present count.
Use a separate unsigned-in browser for access-denial checks.
Reopen today's check-in and use its current code when the case needs an open window.

| Check | Action | Expected result |
| --- | --- | --- |
| Required names | Submit both names empty | First name and family name errors; no attendance |
| Unknown name | Submit a unique name absent from Learners | We could not find that name. Please ask the teacher; no attendance |
| Duplicate sign-in | Submit a learner already signed in | Already signed in; no second attendance and no count increase |
| Closed code | Reload the saved link after Close check-in | Closed message; no new attendance |
| No material grant | Open /materials in a separate unsigned-in browser | No filenames or files; asks for QR sign-in |
| Private file | Link a lesson with one shared file and one staff-only file; sign in a fresh learner | Only the shared file appears |
| No lesson | Unlink the lesson, then sign in a fresh learner | Attendance succeeds; No materials for today |
| Pending review | Link a flagged, unreviewed lesson with a shared file; sign in a fresh learner | Attendance succeeds; Materials will be added soon; no files |
| Existing grant after closure | Close check-in after a successful QR sign-in and revisit /materials on the same browser | Files remain accessible during the 24-hour grant |

For a manually marked learner, a repeated QR attempt can show Already signed in
without issuing a materials grant. This is a current limitation, not proof that
material access works. Use a new learner for the successful scan/download case,
and ask staff for a handout when that limitation occurs.

The four-hour code limit, club-midnight cutoff, 24-hour grant expiry and wrong-name
throttle need separate timed or automated tests. Do not change a shared server's
clock to simulate expiry. Follow the QR, sign-in and materials test scripts in
docs/system_test and the isolated Docker testing instructions in the README.

For each run, record the date, commit, browser/phone, test learner, starting and
ending counts, case result, and any sanitized screenshot or defect reference.
Do not mark a case Pass until its actual result matches the expected result.
Avoid repeating the whole walkthrough with the same already-signed-in learner;
reuse today's session with a fresh unique learner instead.

## 8 Lesson library and cultural review

### 8.1 Create a lesson

**Role:** Teacher or Coordinator. **Entry:** **Lessons** > **New lesson**.

1. Enter a Title.
2. Select the Lesson date.
3. Enter at least one Topic tag, separating tags with commas.
4. Optionally add Teaching notes.
5. Tick **Contains Māori content** when applicable.
6. Optionally select files under **Add materials**.
7. Choose learner sharing for each file if intended.
8. Choose **Save lesson**, then check the lesson detail page.

A lesson is reusable content and is separate from a class session.
Title allows up to 255 characters; each topic tag allows up to 100.
Allowed files are PDF, DOCX, JPG/JPEG and PNG, each up to 10 MiB (10,485,760 bytes).
Other types, oversized or invalid files are refused without clearing the form details.

### 8.2 View and download staff materials

1. Choose **Lessons**.
2. Open a lesson title.
3. Read its date, topic tags, notes and review label.
4. Choose a material's filename to download.

Both staff roles can read shared library lessons. Teachers cannot edit another
teacher's original, but may copy it. Staff can view unreviewed Māori content.

### 8.3 Edit lesson details or files

**Role:** Lesson author or Coordinator.

1. Open the lesson and choose **Edit lesson**.
2. Update title, date, tags or teaching notes.
3. Add new files if required.
4. Choose **Save lesson** and verify the result.
5. On the detail page, change a file's sharing checkbox when needed.
6. To remove a file, choose **Remove file**, then confirm or cancel.

Removing or adding materials resets a reviewed Māori lesson to not yet reviewed.
Changing file sharing does not itself review content.
A removed material can no longer be downloaded through Ako.

Avoid simultaneous edits of the same lesson. The current release does not warn
when another editor's changes would be overwritten.
If a message says details saved but another step failed, inspect the lesson before
retrying: the detail save, content flag and file uploads are separate operations.

### 8.4 Search and filter

1. Open **Lessons**.
2. Type a keyword in **Search lessons**.
3. Optionally choose a **Topic tag**.
4. Read the matching list, or choose **Search** to refresh.
5. Choose **Clear filters** to show all topics and keywords again.

Search covers titles and tags, without regard to letter case; it does not search
inside attached files. A tag and keyword can be combined.
**No lessons found** includes a **Create a new lesson** link.
Use **Refresh** if the lesson list or topic choices need reloading.

### 8.5 Copy a lesson

1. In the list or detail page, choose **Copy as new lesson**.
2. Check the draft title, starting with **Copy of**.
3. Check the copied tags, notes and materials.
4. Remove any unwanted file from the draft using **Remove from copy**.
5. Enter a new Lesson date; the copied draft leaves it blank.
6. Adjust the details, then choose **Save lesson**.
7. Open the saved copy and enable sharing only for files intended for learners.

The original is unchanged. Copied material files start staff-only.
A copied Māori lesson keeps its content flag and requires a new review.
Saving without a date shows **Lesson date is required**.

### 8.6 Flag Māori content

**Role:** Lesson author or Coordinator. **Entry:** lesson editor.

1. Tick **Contains Māori content** for te reo Māori or cultural content.
2. Save.
3. Check **Māori content – not yet reviewed** on the list and detail page.
4. Arrange review through the coordinator before learner sharing.

Unreviewed flagged content stays visible to staff and can be linked to classes,
but its materials are hidden from learners.
Only remove the flag when the content genuinely no longer requires it:
unticking also removes the recorded review.

### 8.7 Record a cultural review

**Role:** Coordinator. **Entry:** flagged lesson detail > **Record a review**.

1. Obtain the review outcome outside Ako.
2. Enter the reviewer's name exactly, including macrons.
3. Enter the review date, today or earlier.
4. Choose **Save review**.
5. Check **Reviewed by [name], [date]**.
6. Confirm the correct files are shared before learners use them.

The reviewer name and date are required; a future date is refused.
Recording a review is not a substitute for consulting the reviewer.
Teachers do not have the review recording form.
If materials change, review the updated content and record a fresh review.

### 8.8 Delete a lesson

**Role:** Lesson author or Coordinator.

1. Open the correct lesson.
2. Choose **Delete lesson**.
3. Read the warning and choose **Confirm deletion**, or **Cancel deletion**.
4. Check that it leaves the active lesson list.

Its files can no longer be downloaded. Classes using it may show
**Lesson unavailable**; choose another lesson for those classes.
Deleting a lesson does not delete the class's attendance.

There is no dedicated lesson export feature. Download attached handouts and use
their application's A4 print options; supported printable output depends on the
document's own formatting.

## 9 A complete class workflow

### 9.1 Before learners arrive

1. Sign in using your own staff account.
2. Check learner records; add newcomers and distinguish same-name people.
3. Create or copy the lesson and upload handouts.
4. Check learner-sharing selections and obtain any Māori content review.
5. Choose **Class sessions** > **Start today's class**.
6. Link the lesson and verify the date.
7. Test the phone URL, then open and display or print QR check-in.

### 9.2 During class

1. Ask learners with phones to complete QR sign-in.
2. Mark learners without phones manually.
3. Watch the Attendance count and handle ambiguous names personally.
4. For a same-name newcomer, add the record through Learners first.
5. Check that QR-signed-in learners can download intended materials.
6. Give manually marked learners a handout directly if online access is unavailable.

### 9.3 After class

1. Check the register and close QR check-in.
2. Print the session list if a paper record is needed.
3. Log out on shared devices.
4. Later, the coordinator corrects past mistakes and checks Change history.
5. Use learner History for follow-up and Attendance reports for date-range exports.
6. Check report scope carefully for newly entered or historically backfilled learners.

## 10 Troubleshooting and current limitations

| Situation | What to do |
| --- | --- |
| You do not have permission | Check the account role. Ask a coordinator for coordinator-only work |
| Login page appears unexpectedly | Sign in again after idle expiry, logout, account deactivation or another login for the same account |
| Name not found at QR sign-in | Check spelling; ask the teacher to identify or add the learner |
| Same name belongs to two people | Ask the teacher to tick the correct record; do not guess using the add-and-mark shortcut |
| Already signed in but no materials | Use the browser with a valid earlier QR grant; otherwise ask staff for the handout |
| Check-in is closed | Ask the teacher whether a new code can be opened for today |
| Phone cannot open the QR address | Ask the maintainer to check network reachability and the configured public origin |
| Materials will be added soon | Staff need to complete the flagged lesson's review; sign-in itself is still recorded |
| No materials for today | Ask staff to link a lesson and check its sharing selections |
| Material is no longer available | Staff may have removed the file/lesson or changed the linked lesson |
| Class or lesson service unavailable | Retry reading; ask the maintainer to check services. A lesson outage can also prevent class pages loading |
| Save or import result is uncertain | Inspect the record/list before retrying; a multi-step operation may have partly succeeded |
| A lesson edit disappeared | Coordinate editing; stale saves currently can overwrite another user's changes |
| History and report totals differ | Check learner creation dates and the selected range; the two views currently apply different scopes |
| Forgotten password or inactive account | Ask the maintainer; there is no self-service password reset or reactivation page |

Today does not have a user-operated class-close action. Use today's register
for current attendance rather than expecting it in the historical view immediately.
There is no offline mode: if the server cannot be reached, keep a paper register
and have a coordinator enter/correct the appropriate past session later.

When asking for support, provide the page, role, class date, steps, time and
sanitized error message. Do not send passwords, material cookies or unnecessary
learner details.

## 11 Feature coverage

| Requirement | Manual section |
| --- | --- |
| US-001 Role-based login and logout | 1 and 3.1–3.2 |
| US-002 Manage staff accounts | 3.3–3.5 |
| US-003 Add and update learner records | 4.1–4.2 |
| US-004 Manual attendance | 6.1–6.3 |
| US-005 Attendance PDF and CSV | 6.6 |
| US-006 Create and edit lessons and materials | 8.1–8.3 and 8.8 |
| US-007 Search and copy lessons | 8.4–8.5 |
| US-008 Māori content review | 8.6–8.7 |
| US-009 Public class information | 2.1 |
| US-010 Submit and view enquiries | 2.2–2.3 |
| US-011 Open, print and close QR check-in | 7.2, 7.4 and 7.7–7.8 |
| US-012 Learner QR sign-in | 7.3 and 7.6–7.8 |
| US-013 Learner materials | 7.1, 7.5 and 7.7–7.8 |
| US-014 Manage class sessions | 5 |
| US-015 Correct past attendance | 6.4 |
| US-016 Learner attendance history | 6.5 |
| US-017 CSV learner import | 4.3 |

The workflow references are the repository's MSE800 User Stories and Ako
Requirements Specification in docs/system_analysis, together with the implemented
page controls and service rules. Installation, testing and maintainer procedures
are kept in the project README so this manual can focus on user tasks.


## 12 Send feedback

**Role:** Anyone, including visitors and learners without an account.
**Entry:** The speech-bubble **Send feedback** icon at the bottom-right of every page.

1. Click or tap the feedback icon. The Feedback page opens.
2. Enter a Title describing the problem or suggestion, up to 200 characters.
3. Enter your valid Email address so staff can reply.
4. Enter a Description, up to 5,000 characters.
5. Choose Submit feedback once and wait for the result.
6. Check for Thank you. Your feedback has been submitted.

All fields are required. Do not include passwords or private learner information.
The form keeps your text after validation or delivery errors and clears it after
a confirmed submission. The submit button is disabled while the request is pending.
You can reach the icon with the keyboard and press Enter. It is hidden when printing.

If feedback is temporarily unavailable, ask the maintainer to check email settings.
For too many requests, wait before trying again. A delivery error does not always
mean no recipient received the message; avoid repeatedly submitting the same text.

The receiving addresses are configured by the maintainer in server/.env and may
include several addresses separated by semicolons. Visitors cannot change that list.
Successful submission means the mail server accepted the message; final inbox
delivery and staff reply times depend on the receiving mail service and staff.
There is no feedback history page or automatic email sent to the visitor.
