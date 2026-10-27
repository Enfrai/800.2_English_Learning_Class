/* Add or edit one learner (UI design document 6.4, parts 3 to 8).
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */

"use client";

import { type FormEvent, type Ref, useEffect, useRef, useState } from "react";
import {
  DuplicateNameError,
  type Learner,
  type LearnerDetails,
  LearnerFieldError,
  LoginRequiredError,
  addLearner,
  updateLearner,
} from "@/lib/learners-api";

const MAX_NAME_LENGTH = 100;
const MAX_LANGUAGE_LENGTH = 100;
const MAX_CONTACT_LENGTH = 255;

// Message catalogue, UI design document section 7.
const FIRST_NAME_REQUIRED = "First name is required";
const FAMILY_NAME_REQUIRED = "Family name is required";
const NAME_TOO_LONG = "Name must be 100 characters or fewer";
const SAVE_FAILED = "The learner could not be saved. Please try again.";

export type FieldName = keyof LearnerDetails;
export type FieldErrors = Partial<Record<FieldName, string>>;

const FIELD_IDS: Record<FieldName, string> = {
  first_name: "learner-first-name",
  family_name: "learner-family-name",
  first_language: "learner-first-language",
  contact: "learner-contact",
};

/*
 * Validate learner name fields before submitting the form.
 */
export function checkNames(details: LearnerDetails): FieldErrors {
  const errors: FieldErrors = {};
  const firstName = details.first_name.trim();
  const familyName = details.family_name.trim();
  if (!firstName) errors.first_name = FIRST_NAME_REQUIRED;
  else if (firstName.length > MAX_NAME_LENGTH) errors.first_name = NAME_TOO_LONG;
  if (!familyName) errors.family_name = FAMILY_NAME_REQUIRED;
  else if (familyName.length > MAX_NAME_LENGTH) errors.family_name = NAME_TOO_LONG;
  return errors;
}

type Props = {
  /** The learner to edit, or null to add a new one. */
  learner: Learner | null;
  onSaved: () => void;
  onCancel: () => void;
  onLoginRequired: () => void;
};

/*
 * Render the learner form interface and its associated content.
 */
export default function LearnerForm({ learner, onSaved, onCancel, onLoginRequired }: Props) {
  const [details, setDetails] = useState<LearnerDetails>({
    first_name: learner?.first_name ?? "",
    family_name: learner?.family_name ?? "",
    first_language: learner?.first_language ?? "",
    contact: learner?.contact ?? "",
  });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  const editing = learner !== null;
  const heading = editing ? "Edit learner" : "Add learner";

  useEffect(/*
     * Synchronize the component with its current dependencies and manage effect
     * resources.
     */
    () => {
    firstFieldRef.current?.focus();
  }, []);

  /*
   * Update the edited form field and clear its obsolete feedback.
   */
  function change(field: FieldName, value: string) {
    setDetails(/*
     * Compute the next details state from its previous value.
     */
    (current) => ({ ...current, [field]: value }));
    setErrors(/*
     * Compute the next errors state from its previous value.
     */
    (current) => ({ ...current, [field]: undefined }));
    // The warning was about the old name.
    if (field === "first_name" || field === "family_name") setDuplicateWarning(null);
  }

  /*
   * Validate and submit the learner form form, updating its success and error state.
   */
  async function save(allowDuplicate: boolean) {
    if (saving) return;
    const found = checkNames(details);
    setErrors(found);
    setFailure(null);
    const firstInvalid = (Object.keys(FIELD_IDS) as FieldName[]).find(/*
     * Find the collection entry matching the selected identifier or condition.
     */
    (field) => found[field]);
    if (firstInvalid) {
      document.getElementById(FIELD_IDS[firstInvalid])?.focus();
      return;
    }

    setSaving(true);
    setDuplicateWarning(null);
    try {
      if (learner) await updateLearner(learner.id, details, allowDuplicate);
      else await addLearner(details, allowDuplicate);
      onSaved();
    } catch (error) {
      if (error instanceof DuplicateNameError) setDuplicateWarning(error.message);
      else if (error instanceof LearnerFieldError && error.field in FIELD_IDS) {
        setErrors({ [error.field]: error.message });
      } else if (error instanceof LoginRequiredError) onLoginRequired();
      else setFailure(SAVE_FAILED);
    } finally {
      setSaving(false);
    }
  }

  /*
   * Validate and submit the learner form form, updating its success and error state.
   */
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void save(false);
  }

  return (
    <section aria-labelledby="learner-form-title" className="no-print">
      <h2 id="learner-form-title">{heading}</h2>
      <form onSubmit={submit} noValidate aria-busy={saving}>
        <div className="grid-2">
          <TextField
            ref={firstFieldRef}
            name="first_name"
            label="First name"
            required
            value={details.first_name}
            error={errors.first_name}
            onChange={change}
          />
          <TextField
            name="family_name"
            label="Family name"
            required
            value={details.family_name}
            error={errors.family_name}
            onChange={change}
          />
          <TextField
            name="first_language"
            label="First language"
            maxLength={MAX_LANGUAGE_LENGTH}
            value={details.first_language}
            error={errors.first_language}
            onChange={change}
          />
          <TextField
            name="contact"
            label="Phone or email"
            hint="Only if the learner agrees"
            maxLength={MAX_CONTACT_LENGTH}
            value={details.contact}
            error={errors.contact}
            onChange={change}
          />
        </div>
        <div className="row">
          <button type="submit" className="btn">
            {saving ? "Saving…" : "Save"}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            Cancel
          </button>
        </div>
        {duplicateWarning && (
          <div className="msg msg-warning" role="alert">
            {duplicateWarning}.{" "}
            <button type="button" className="btn btn-secondary" onClick={/*
     * Handle the click event for this control.
     */
    () => setDuplicateWarning(null)}>
              Cancel
            </button>{" "}
            <button type="button" className="btn" onClick={/*
     * Handle the click event for this control.
     */
    () => void save(true)}>
              {editing ? "Save anyway" : "Add anyway"}
            </button>
          </div>
        )}
        {failure && (
          <div className="msg msg-error" role="alert">
            {failure}
          </div>
        )}
      </form>
    </section>
  );
}

type TextFieldProps = {
  ref?: Ref<HTMLInputElement>;
  name: FieldName;
  label: string;
  value: string;
  error?: string;
  hint?: string;
  required?: boolean;
  maxLength?: number;
  onChange: (field: FieldName, value: string) => void;
};

/*
 * Render the text field interface and its associated content.
 */
export function TextField({ ref, name, label, value, error, hint, required, maxLength, onChange }: TextFieldProps) {
  const id = FIELD_IDS[name];
  const describedBy = [error && `${id}-error`, hint && `${id}-hint`].filter(Boolean).join(" ");
  return (
    <div className={error ? "field invalid" : "field"}>
      <label className={required ? "req" : undefined} htmlFor={id}>
        {label}
      </label>
      <input
        ref={ref}
        id={id}
        type="text"
        autoComplete="off"
        value={value}
        maxLength={maxLength}
        aria-required={required}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy || undefined}
        onChange={/*
     * Handle the change event for this control.
     */
    (event) => onChange(name, event.target.value)}
      />
      {hint && (
        <div id={`${id}-hint`} className="hint">
          {hint}
        </div>
      )}
      {error && (
        <div id={`${id}-error`} className="msg msg-error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
