/*
 * Upload a learner CSV and display imported rows, duplicates and validation errors.
 * Author: Leonwu2026
 * Date: 25 Oct 2026
 */

"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useId, useRef, useState } from "react";

const MAX_BYTES = 1_048_576;
const SIZE_ERROR = "CSV file must be 1,048,576 bytes or fewer";
const TEMPLATE = "first_name,family_name,first_language,contact\r\n";

type Duplicate = { row_number: number; first_name: string; family_name: string; source: "file" | "database"; first_row_number: number | null };
type RowError = { row_number: number; field: string; message: string };
type ImportResult = { imported_count: number; duplicates: Duplicate[]; errors: RowError[] };

/** Validate the response before presenting a committed import as successful. */
function isResult(value: unknown): value is ImportResult {
  if (!value || typeof value !== "object") return false;
  const result = value as ImportResult;
  return Number.isSafeInteger(result.imported_count) && result.imported_count >= 0
    && Array.isArray(result.duplicates) && result.duplicates.every(/*
     * Check whether every collection entry satisfies this validation rule.
     */
    row => row && Number.isSafeInteger(row.row_number) && row.row_number > 1
      && typeof row.first_name === "string" && typeof row.family_name === "string"
      && ["file", "database"].includes(row.source))
    && Array.isArray(result.errors) && result.errors.every(/*
     * Check whether every collection entry satisfies this validation rule.
     */
    row => row && Number.isSafeInteger(row.row_number) && row.row_number > 1
      && typeof row.field === "string" && typeof row.message === "string");
}

/** Mount inside the authenticated Coordinator area. The API enforces role and CSRF;
 * this standalone component is not an authorization boundary or a session provider.
 */
export default function CsvUpload({ onImported }: { onImported?: () => void }) {
  const router = useRouter();
  const id = useId();
  const picker = useRef<HTMLInputElement>(null);
  const pending = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);

  /*
   * Validate and submit the csv upload form, updating its success and error state.
   */
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current || blocked) return;
    setResult(null);
    const problem = !file ? "Choose a CSV file" : !file.name.toLowerCase().endsWith(".csv")
      ? "File must be a CSV file (.csv)" : file.size > MAX_BYTES ? SIZE_ERROR : "";
    setError(problem);
    if (problem) { picker.current?.focus(); return; }
    pending.current = true;
    setBusy(true);
    try {
      const data = new FormData();
      data.append("file", file!);
      // Let the browser supply the multipart boundary, same-origin cookie and Origin.
      // Never copy session tokens to JavaScript storage or manually set Authorization.
      const response = await fetch("/api/user/learners/import", {
        method: "POST", body: data, credentials: "same-origin", cache: "no-store",
      });
      if (response.status === 401 || response.status === 403) {
        setBlocked(true);
        setFile(null);
        if (picker.current) picker.current.value = "";
        if (response.status === 401) {
          setError("Your session has expired. Please sign in again.");
          router.replace("/");
        } else setError("You do not have permission");
        return;
      }
      if (response.status === 413) { setError(SIZE_ERROR); return; }
      const body: unknown = await response.json().catch(/*
     * Handle an asynchronous failure using the workflow’s error state.
     */
    () => null);
      if (!response.ok) {
        const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
        // Only display the parser's known file-error messages, not arbitrary server content.
        const known = typeof detail === "string" && (
          ["CSV file must use UTF-8 encoding", "File must be a CSV file (.csv)", "CSV file must not contain NUL characters",
            "CSV header must be: first_name,family_name,first_language,contact"].includes(detail)
          || /^CSV row \d+ must contain exactly 4 columns$/.test(detail)
          || /^Invalid CSV format near row \d+$/.test(detail));
        setError(response.status === 422 ? known ? detail as string : "Invalid CSV file. Check the template and UTF-8 encoding."
          : response.status === 500 && detail === "Unable to import learners. No learners were imported." ? detail
          : "Unable to confirm the import. Check the learner list before retrying.");
        return;
      }
      if (!isResult(body)) throw new Error("Invalid import response");
      setResult(body);
      // Refresh the parent list only after a validated successful response.
      onImported?.();
      // Prevent an accidental second import of the successfully processed file.
      setFile(null);
      if (picker.current) picker.current.value = "";
    } catch {
      // A lost response does not prove rollback; do not automatically retry writes.
      setError("Unable to confirm the import. Check the learner list before retrying.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <section aria-labelledby={`${id}-title`} style={{ overflowWrap: "anywhere" }}>
    <h2 id={`${id}-title`}>Import learners from CSV</h2>
    <p id={`${id}-help`}>UTF-8 CSV, up to 1 MiB (1,048,576 bytes). Names are required and must be 100 characters or fewer. First language and contact are optional. The header is row 1.</p>
    <a className="btn btn-secondary" download="learners-template.csv" href={`data:text/csv;charset=utf-8,${encodeURIComponent(TEMPLATE)}`}>Download CSV template</a>
    <form onSubmit={submit} noValidate aria-busy={busy}>
      <div className="field">
        <label htmlFor={`${id}-file`}>CSV file</label>
        <input ref={picker} id={`${id}-file`} type="file" accept=".csv,text/csv" disabled={busy || blocked}
          aria-describedby={`${id}-help`} style={{ maxWidth: "100%", minHeight: "var(--control-h)" }}
          onChange={/*
     * Handle the change event for this control.
     */
    event => { setFile(event.target.files?.[0] ?? null); setResult(null); setError(""); }} />
      </div>
      <button className="btn" disabled={busy || blocked} type="submit">{busy ? "Importing…" : "Import learners"}</button>
      {busy && <p role="status">Uploading CSV…</p>}
      {error && <p className="msg msg-error" role="alert">{error}</p>}
    </form>
    {result && <div>
      <p className="msg msg-success" role="status">{result.imported_count} learners imported</p>
      {result.duplicates.length > 0 && <div className="msg msg-warning">
        <h3>Skipped duplicate learners ({result.duplicates.length})</h3>
        <ul>{result.duplicates.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    row => <li key={row.row_number}>Row {row.row_number}: {row.first_name} {row.family_name} — {row.source === "database" ? "Already exists" : `Duplicate in file${row.first_row_number ? ` (row ${row.first_row_number})` : ""}`}</li>)}</ul>
      </div>}
      {result.errors.length > 0 && <div className="msg msg-error" role="alert">
        <h3>Rejected rows ({result.errors.length})</h3>
        <ul>{result.errors.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    row => <li key={`${row.row_number}-${row.field}`}>Row {row.row_number}: {row.message}</li>)}</ul>
      </div>}
    </div>}
  </section>;
}
