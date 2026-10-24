/* Add or edit a lesson: title, date, topic tags and files (UI design document 6.8).
 * A file that breaks the rule is refused with the rule, and the title, date
 * and tags already entered stay on the form (US-006 AC4).
 * Author: Sandhya Tiwari
 * Date: 23 Oct 2026
 */

"use client";

import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";
import { ACCEPT_FILES, checkFile, FILE_RULE, formatSize } from "./file-rule";
import {
  type Lesson,
  type LessonDetails,
  LessonFieldError,
  LoginRequiredError,
  NoPermissionError,
  addLesson,
  listTags,
  updateLesson,
  uploadMaterial,
} from "@/lib/lessons-api";

const MAX_TITLE_LENGTH = 255;

// Message catalogue, UI design document section 7 and Test Plan UT-39.
const TITLE_REQUIRED = "Title is required";
const TITLE_TOO_LONG = "Title must be 255 characters or fewer";
const DATE_REQUIRED = "Lesson date is required";
const TAG_REQUIRED = "Choose at least one topic tag";
const NO_PERMISSION = "You do not have permission";
const SAVE_FAILED = "The lesson could not be saved. Please try again.";

type FieldName = "title" | "lesson_date" | "tags" | "file";
type FieldErrors = Partial<Record<FieldName, string>>;

const FIELD_IDS: Record<FieldName, string> = {
  title: "lesson-title",
  lesson_date: "lesson-date",
  tags: "lesson-tags",
  file: "lesson-files",
};

/** A chosen file that has not been uploaded yet. */
type PendingFile = { key: string; file: File; share: boolean };

export function checkDetails(details: LessonDetails): FieldErrors {
  const errors: FieldErrors = {};
  const title = details.title.trim();
  if (!title) errors.title = TITLE_REQUIRED;
  else if (title.length > MAX_TITLE_LENGTH) errors.title = TITLE_TOO_LONG;
  if (!details.lesson_date) errors.lesson_date = DATE_REQUIRED;
  if (details.tags.length === 0) errors.tags = TAG_REQUIRED;
  return errors;
}

type Props = {
  /** The lesson to edit, or null to add a new one. */
  lesson: Lesson | null;
};

export default function LessonForm({ lesson }: Props) {
  const [details, setDetails] = useState<LessonDetails>({
    title: lesson?.title ?? "",
    lesson_date: lesson?.lesson_date ?? "",
    tags: lesson?.tags ?? [],
  });
  const [tagOptions, setTagOptions] = useState<string[]>([]);
  const [pending, setPending] = useState<PendingFile[]>([]);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loginRequired, setLoginRequired] = useState(false);
  // Once saved, a later file problem must not create the lesson a second time.
  const [savedId, setSavedId] = useState<string | null>(lesson?.id ?? null);
  const titleRef = useRef<HTMLInputElement>(null);

  const editing = lesson !== null;

  useEffect(() => {
    titleRef.current?.focus();
    listTags()
      .then(setTagOptions)
      .catch((error) => {
        if (error instanceof LoginRequiredError) setLoginRequired(true);
        else setFailure(SAVE_FAILED);
      });
  }, []);

  function change(field: "title" | "lesson_date", value: string) {
    setDetails((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  function toggleTag(tag: string, checked: boolean) {
    setDetails((current) => ({
      ...current,
      tags: checked ? [...current.tags, tag] : current.tags.filter((name) => name !== tag),
    }));
    setErrors((current) => ({ ...current, tags: undefined }));
  }

  function chooseFiles(event: ChangeEvent<HTMLInputElement>) {
    const chosen = Array.from(event.target.files ?? []);
    // Clear the chooser so the same file can be chosen again after a fix.
    event.target.value = "";
    const refused = chosen.filter((file) => checkFile(file));
    const accepted = chosen.filter((file) => !checkFile(file));
    setPending((current) => [
      ...current,
      ...accepted.map((file) => ({ key: `${file.name}-${file.size}-${Math.random()}`, file, share: false })),
    ]);
    setErrors((current) => ({
      ...current,
      file: refused.length > 0 ? `${refused.map((file) => file.name).join(", ")}: ${FILE_RULE}` : undefined,
    }));
  }

  function setShare(key: string, share: boolean) {
    setPending((current) => current.map((item) => (item.key === key ? { ...item, share } : item)));
  }

  function removePending(key: string) {
    setPending((current) => current.filter((item) => item.key !== key));
  }

  async function save() {
    if (saving) return;
    const found = checkDetails(details);
    setErrors(found);
    setFailure(null);
    const firstInvalid = (Object.keys(FIELD_IDS) as FieldName[]).find((field) => found[field]);
    if (firstInvalid) {
      document.getElementById(FIELD_IDS[firstInvalid])?.focus();
      return;
    }

    setSaving(true);
    try {
      let lessonId = savedId;
      if (lessonId) await updateLesson(lessonId, details);
      else {
        lessonId = (await addLesson(details)).id;
        setSavedId(lessonId);
      }
      // Upload one at a time; a refused file stays listed so it can be removed.
      for (const item of pending) {
        try {
          await uploadMaterial(lessonId, item.file, item.share);
          setPending((current) => current.filter((other) => other.key !== item.key));
        } catch (error) {
          if (error instanceof LessonFieldError && error.field === "file") {
            setErrors({ file: `${item.file.name}: ${error.message}` });
            document.getElementById(FIELD_IDS.file)?.focus();
            return;
          }
          throw error;
        }
      }
      window.location.assign(`/lessons/${lessonId}?notice=saved`);
    } catch (error) {
      if (error instanceof LessonFieldError && error.field in FIELD_IDS) {
        setErrors({ [error.field]: error.message });
        document.getElementById(FIELD_IDS[error.field as FieldName])?.focus();
      } else if (error instanceof LoginRequiredError) setLoginRequired(true);
      else if (error instanceof NoPermissionError) setFailure(NO_PERMISSION);
      else setFailure(SAVE_FAILED);
    } finally {
      setSaving(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void save();
  }

  if (loginRequired) {
    return (
      <div className="msg msg-error" role="alert">
        Please log in to save lessons. <a href="/">Log in</a>
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate aria-busy={saving} className="no-print">
      <div className="grid-2">
        <div className={errors.title ? "field invalid" : "field"}>
          <label className="req" htmlFor={FIELD_IDS.title}>
            Title
          </label>
          <input
            ref={titleRef}
            id={FIELD_IDS.title}
            type="text"
            autoComplete="off"
            value={details.title}
            maxLength={MAX_TITLE_LENGTH + 1}
            aria-required
            aria-invalid={Boolean(errors.title)}
            aria-describedby={errors.title ? `${FIELD_IDS.title}-error` : undefined}
            onChange={(event) => change("title", event.target.value)}
          />
          <FieldError id={FIELD_IDS.title} message={errors.title} />
        </div>
        <div className={errors.lesson_date ? "field invalid" : "field"}>
          <label className="req" htmlFor={FIELD_IDS.lesson_date}>
            Lesson date
          </label>
          <input
            id={FIELD_IDS.lesson_date}
            type="date"
            value={details.lesson_date}
            aria-required
            aria-invalid={Boolean(errors.lesson_date)}
            aria-describedby={errors.lesson_date ? `${FIELD_IDS.lesson_date}-error` : undefined}
            onChange={(event) => change("lesson_date", event.target.value)}
          />
          <FieldError id={FIELD_IDS.lesson_date} message={errors.lesson_date} />
        </div>
      </div>

      <fieldset
        id={FIELD_IDS.tags}
        tabIndex={-1}
        className={errors.tags ? "field invalid" : "field"}
        aria-describedby={errors.tags ? `${FIELD_IDS.tags}-error` : `${FIELD_IDS.tags}-hint`}
        style={{ border: 0, padding: 0, margin: "0 0 var(--space-3)" }}
      >
        <legend className="req" style={{ fontWeight: 700, marginBottom: "var(--space-1)" }}>
          Topic tags
        </legend>
        <div id={`${FIELD_IDS.tags}-hint`} className="hint">
          Choose one or more
        </div>
        <div className="row">
          {tagOptions.map((tag) => (
            <label key={tag} className="check">
              <input
                type="checkbox"
                checked={details.tags.includes(tag)}
                onChange={(event) => toggleTag(tag, event.target.checked)}
              />
              <span style={{ paddingTop: 8 }}>{tag}</span>
            </label>
          ))}
        </div>
        <FieldError id={FIELD_IDS.tags} message={errors.tags} />
      </fieldset>

      <div className={errors.file ? "field invalid" : "field"}>
        <label htmlFor={FIELD_IDS.file}>{editing ? "Add files" : "Files"}</label>
        <input
          id={FIELD_IDS.file}
          type="file"
          multiple
          accept={ACCEPT_FILES}
          aria-describedby={[errors.file && `${FIELD_IDS.file}-error`, `${FIELD_IDS.file}-hint`]
            .filter(Boolean)
            .join(" ")}
          onChange={chooseFiles}
        />
        <div id={`${FIELD_IDS.file}-hint`} className="hint">
          PDF, DOCX, JPG or PNG, from 1 KB to 10 MB each
        </div>
        <FieldError id={FIELD_IDS.file} message={errors.file} />
      </div>

      {pending.length > 0 && (
        <table className="data" aria-label="Files to upload" style={{ marginBottom: "var(--space-4)" }}>
          <thead>
            <tr>
              <th scope="col">File</th>
              <th scope="col">Size</th>
              <th scope="col">Share with learners</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {pending.map((item) => (
              <tr key={item.key}>
                <td>{item.file.name}</td>
                <td>{formatSize(item.file.size)}</td>
                <td>
                  {/* Off by default, so nothing is shared until a teacher ticks it (US-013). */}
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={item.share}
                      aria-label={`Share ${item.file.name} with learners`}
                      onChange={(event) => setShare(item.key, event.target.checked)}
                    />
                  </label>
                </td>
                <td>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    aria-label={`Remove ${item.file.name}`}
                    onClick={() => removePending(item.key)}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="row">
        <button type="submit" className="btn">
          {saving ? "Saving…" : "Save"}
        </button>
        <a className="btn btn-secondary" href={savedId ? `/lessons/${savedId}` : "/lessons"}>
          Cancel
        </a>
      </div>
      {failure && (
        <div className="msg msg-error" role="alert">
          {failure}
        </div>
      )}
    </form>
  );
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <div id={`${id}-error`} className="msg msg-error" role="alert">
      {message}
    </div>
  );
}
