import { apiRequest, LoginRequiredError } from "./api";

export { LoginRequiredError };
export const MAX_MATERIAL_BYTES = 10 * 1024 * 1024;
export const MATERIAL_RULE = "Use PDF, DOCX, JPG or PNG files, up to 10 MB (10,485,760 bytes) each";
export type Material = {
  id: string; lesson_id: string; file_name: string; mime_type: string;
  file_size: number; share_with_learners: boolean; created_at: string;
};
export type Lesson = {
  id: string; title: string; lesson_date: string; description: string | null;
  created_by: string; tags: string[]; materials: Material[];
  can_edit: boolean;
  /** US-008: "pending" until a coordinator records the review, then "reviewed". */
  has_maori_content: boolean; review_status: "not_required" | "pending" | "reviewed";
  review_label: string | null;
};
export type LessonInput = { title: string; lesson_date: string; description: string; tags: string[] };
export class LessonError extends Error {
  constructor(message: string, public fields: Record<string, string> = {}) { super(message); }
}
async function send<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { status, body, message, detail } = await apiRequest("/api/lesson/" + path, init);
  if (status >= 200 && status < 300) return body as T;
  if (status === 403) throw new LessonError("You do not have permission");
  if (status === 404) throw new LessonError("This lesson or material is no longer available");
  if (status === 409) throw new LessonError(message || "The source lesson changed. Reopen the copy draft.");
  if (status === 413) throw new LessonError(MATERIAL_RULE);
  // US-008: a review for a lesson that is no longer marked as Māori content.
  if (status === 409 && message) throw new LessonError(message);
  if (status === 422) {
    const fields: Record<string, string> = {};
    if (detail?.errors && typeof detail.errors === "object") {
      for (const [key, value] of Object.entries(detail.errors)) {
        if (typeof value === "string") fields[key] = value;
      }
    }
    throw new LessonError(message || "Please check the form fields", fields);
  }
  throw new LessonError("Unable to complete the request. Please try again.");
}
export type LessonSearch = { q?: string; tag?: string };
export type CopyDraft = {
  source_lesson_id: string; title: string; lesson_date: null; description: string;
  tags: string[]; materials: Material[]; has_maori_content: boolean;
};
export const listLessons = (filters: LessonSearch = {}) => {
  const params = new URLSearchParams();
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.tag?.trim()) params.set("tag", filters.tag.trim());
  return send<Lesson[]>("lessons" + (params.size ? "?" + params.toString() : ""));
};
export const getCopyDraft = (id: string) => send<CopyDraft>(`lessons/${encodeURIComponent(id)}/copy`);
export const copyLesson = (id: string, input: LessonInput, materialIds: string[]) =>
  send<Lesson>(`lessons/${encodeURIComponent(id)}/copy`, {
    method: "POST", body: JSON.stringify({ ...input, material_ids: materialIds }),
  });
export const getLesson = (id: string) => send<Lesson>(`lessons/${encodeURIComponent(id)}`);
export const listTags = () => send<{ id: string; name: string }[]>("tags");
export const saveLesson = (id: string | null, input: LessonInput) =>
  send<Lesson>(id ? `lessons/${encodeURIComponent(id)}` : "lessons", {
    method: id ? "PUT" : "POST", body: JSON.stringify(input),
  });
export const deleteLesson = (id: string) => send<void>(`lessons/${encodeURIComponent(id)}`, { method: "DELETE" });
export function uploadMaterial(id: string, file: File, share: boolean) {
  const body = new FormData();
  body.append("file", file);
  body.append("share_with_learners", String(share));
  return send<Material>(`lessons/${encodeURIComponent(id)}/materials`, { method: "POST", body });
}
export const deleteMaterial = (id: string) => send<void>(`materials/${encodeURIComponent(id)}`, { method: "DELETE" });
export const shareMaterial = (id: string, value: boolean) => send<Material>(`materials/${encodeURIComponent(id)}`, {
  method: "PATCH", body: JSON.stringify({ share_with_learners: value }),
});
/** Tick or untick "Contains Māori content" (US-008). Lesson author or coordinator. */
export const setMaoriContent = (id: string, value: boolean) => send<unknown>(`lessons/${encodeURIComponent(id)}/maori-content`, {
  method: "PUT", body: JSON.stringify({ has_maori_content: value }),
});
/** Record a Māori content review (US-008). Coordinators only; 422 gives each field's message. */
export const recordReview = (id: string, review: { reviewer_name: string; review_date: string }) =>
  send<unknown>(`lessons/${encodeURIComponent(id)}/review`, {
    method: "POST", body: JSON.stringify({ ...review, review_date: review.review_date || null }),
  });
export const materialUrl = (id: string) => `/api/staff/lesson/materials/${encodeURIComponent(id)}/download`;
export const messageFor = (error: unknown) => error instanceof LessonError ? error.message : "Unable to complete the request. Please try again.";
