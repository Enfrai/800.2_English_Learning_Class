/* Call the Lesson Service endpoints through Nginx (US-006).
 * Author: Sandhya Tiwari
 * Date: 23 Oct 2026
 * Updated: 24 Oct 2026 (open files in the browser, file counts, review status)
 */

import { apiFile, apiRequest, RequestFailedError } from "./api";

export { LoginRequiredError, RequestFailedError } from "./api";

const LESSON_API = "/api/lesson";

export type LessonSummary = {
  id: string;
  title: string;
  lesson_date: string;
  tags: string[];
  created_by: string;
  /** True when the logged-in user is the author or a coordinator. */
  can_change: boolean;
  updated_at: string;
  /** Files that can be downloaded. */
  material_count: number;
  /** US-008: "Māori content – not yet reviewed" shows until reviewed. */
  has_maori_content: boolean;
  review_status: "not_required" | "pending" | "reviewed" | "rejected";
};

export type Material = {
  id: string;
  file_name: string;
  mime_type: string;
  file_size: number;
  share_with_learners: boolean;
  created_at: string;
};

export type Lesson = LessonSummary & { materials: Material[] };

export type LessonDetails = {
  title: string;
  /** "YYYY-MM-DD", or "" when not chosen. */
  lesson_date: string;
  tags: string[];
};

/** One field breaks a rule. The message comes from the server. */
export class LessonFieldError extends Error {
  readonly field: string;

  constructor(field: string, message: string) {
    super(message);
    this.field = field;
  }
}

/** The user is not the author or a coordinator. */
export class NoPermissionError extends Error {}

/** The lesson or file does not exist, or was deleted. */
export class NotFoundError extends Error {}

async function send<T>(url: string, init: RequestInit = {}): Promise<T> {
  const { status, body, detail, message } = await apiRequest(url, init);
  if (status >= 200 && status < 300) return body as T;
  if (status === 422 && typeof detail?.field === "string") {
    throw new LessonFieldError(detail.field, String(detail.message));
  }
  if (status === 403) throw new NoPermissionError(message ?? "You do not have permission");
  if (status === 404) throw new NotFoundError(message ?? "Not found");
  throw new RequestFailedError();
}

function lessonUrl(id: string): string {
  return `${LESSON_API}/lessons/${encodeURIComponent(id)}`;
}

function materialUrl(id: string): string {
  return `${LESSON_API}/materials/${encodeURIComponent(id)}`;
}

function detailsBody(details: LessonDetails): string {
  return JSON.stringify({
    title: details.title,
    lesson_date: details.lesson_date || null,
    tags: details.tags,
  });
}

export function listTags(): Promise<string[]> {
  return send<string[]>(`${LESSON_API}/tags`);
}

export function listLessons(): Promise<LessonSummary[]> {
  return send<LessonSummary[]>(`${LESSON_API}/lessons`);
}

export function getLesson(id: string): Promise<Lesson> {
  return send<Lesson>(lessonUrl(id));
}

export function addLesson(details: LessonDetails): Promise<Lesson> {
  return send<Lesson>(`${LESSON_API}/lessons`, { method: "POST", body: detailsBody(details) });
}

export function updateLesson(id: string, details: LessonDetails): Promise<Lesson> {
  return send<Lesson>(lessonUrl(id), { method: "PUT", body: detailsBody(details) });
}

export async function deleteLesson(id: string): Promise<void> {
  await send<null>(lessonUrl(id), { method: "DELETE" });
}

export function uploadMaterial(lessonId: string, file: File, shareWithLearners: boolean): Promise<Material> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("share_with_learners", shareWithLearners ? "true" : "false");
  return send<Material>(`${lessonUrl(lessonId)}/materials`, { method: "POST", body: form });
}

export function setShareWithLearners(materialId: string, share: boolean): Promise<Material> {
  return send<Material>(materialUrl(materialId), {
    method: "PATCH",
    body: JSON.stringify({ share_with_learners: share }),
  });
}

export async function removeMaterial(materialId: string): Promise<void> {
  await send<null>(materialUrl(materialId), { method: "DELETE" });
}

async function fetchMaterial(material: Material): Promise<Blob> {
  const { status, blob } = await apiFile(`${materialUrl(material.id)}/download`);
  if (status === 404) throw new NotFoundError("File not found");
  if (!blob) throw new RequestFailedError();
  return blob;
}

/** Types a browser can show itself. A Word file is always downloaded. */
const OPENABLE_TYPES = ["application/pdf", "image/jpeg", "image/png"];

export function canOpenInBrowser(material: Material): boolean {
  return OPENABLE_TYPES.includes(material.mime_type);
}

/**
 * Open a PDF or picture in a new tab.
 * The tab must be opened by the click itself, before any waiting, or the
 * browser blocks it as a pop-up; it is filled once the file has arrived.
 */
export async function openMaterial(material: Material): Promise<void> {
  const tab = window.open("", "_blank");
  try {
    const blob = await fetchMaterial(material);
    const url = URL.createObjectURL(new Blob([blob], { type: material.mime_type }));
    if (tab) tab.location.href = url;
    else window.location.assign(url);
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (error) {
    tab?.close();
    throw error;
  }
}

/** Download a file and save it under its original name (US-006 AC3). */
export async function downloadMaterial(material: Material): Promise<void> {
  const blob = await fetchMaterial(material);
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = material.file_name;
  document.body.append(link);
  link.click();
  link.remove();
  // Give the browser time to start the download before the address is freed.
  setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
}
