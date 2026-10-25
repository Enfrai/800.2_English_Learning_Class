/* The lesson file rule, checked in the browser before uploading (US-006 AC4).
 * The Lesson Service checks the same rule again (server/services/lesson/files.py);
 * keep the two in step.
 * Author: Sandhya Tiwari
 * Date: 23 Oct 2026
 */

const KB = 1024;
const MB = 1024 * KB;
export const MIN_FILE_BYTES = 1 * KB;
export const MAX_FILE_BYTES = 10 * MB;
const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".jpg", ".jpeg", ".png"];

// Message catalogue: one message that states the whole rule.
export const FILE_RULE = "Files must be PDF, DOCX, JPG or PNG, from 1 KB to 10 MB";

/** Used by the file chooser so it offers only the allowed types. */
export const ACCEPT_FILES = ALLOWED_EXTENSIONS.join(",");

/** Return the rule message when the file breaks the rule, otherwise null. */
export function checkFile(file: File): string | null {
  const dot = file.name.lastIndexOf(".");
  const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!ALLOWED_EXTENSIONS.includes(extension)) return FILE_RULE;
  if (file.size < MIN_FILE_BYTES || file.size > MAX_FILE_BYTES) return FILE_RULE;
  return null;
}

/** "2.4 MB" or "850 KB", for the file list. */
export function formatSize(bytes: number): string {
  if (bytes >= MB) return `${(bytes / MB).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / KB))} KB`;
}

/** "21 Oct 2026" from "2026-10-21", without time zone shifts. */
export function formatLessonDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-NZ", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}
