/* Call protected class-session APIs with the staff cookie adapter (US-014).
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

import { apiRequest, LoginRequiredError } from "./api";
export { LoginRequiredError };
export type ClassSession = {
  id: string; session_date: string; lesson_id: string | null; lesson_title: string | null;
  lesson_unavailable: boolean; attendance_count: number; present_count: number; can_delete: boolean;
};
export type SessionList = { today: string; sessions: ClassSession[] };
export type SessionDetails = ClassSession & { today: string };
export type StartedSession = { id: string; session_date: string; created: boolean };
export class ClassSessionError extends Error {
  constructor(message: string, public field?: string, public status?: number) { super(message); }
}
async function send<T>(path: string, init: RequestInit = {}): Promise<T> {
  const reply = await apiRequest("/api/access/sessions" + path, init);
  if (reply.status >= 200 && reply.status < 300) return reply.body as T;
  if (reply.status === 403) throw new ClassSessionError("You do not have permission", undefined, 403);
  const message = typeof reply.detail?.message === "string" ? reply.detail.message : reply.message;
  const field = typeof reply.detail?.field === "string" ? reply.detail.field : undefined;
  throw new ClassSessionError(message || "The class could not be updated. Please try again.", field, reply.status);
}
export const listClassSessions = () => send<SessionList>("");
export const getClassSession = (id: string) => send<SessionDetails>(`/${encodeURIComponent(id)}`);
export const startToday = () => send<StartedSession>("/today", { method: "POST" });
export const createClassSession = (day: string) => send<StartedSession>("", { method: "POST", body: JSON.stringify({ session_date: day }) });
export const linkClassLesson = (id: string, lesson: string | null) => send<ClassSession>(`/${encodeURIComponent(id)}/lesson`, { method: "PUT", body: JSON.stringify({ lesson_id: lesson }) });
export const deleteClassSession = (id: string) => send<void>(`/${encodeURIComponent(id)}`, { method: "DELETE" });
export const sessionError = (error: unknown) => error instanceof ClassSessionError ? error.message : "The class could not be updated. Please try again.";
