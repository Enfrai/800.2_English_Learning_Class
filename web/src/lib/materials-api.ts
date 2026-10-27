/*
 * Load and download learner-shared materials using the browser grant cookie.
 * Author: SandhyaCodes1
 * Date: 26 Oct 2026
 */

export type Material = { id: string; file_name: string; file_size: number };
export type Materials = { session_date: string; materials: Material[]; message: string };
export class SignInRequired extends Error {}
/*
 * Load shared class materials using the learner grant cookie.
 */
export async function getMaterials(): Promise<Materials> {
  const response = await fetch("/api/access/learner/materials", { credentials: "same-origin", cache: "no-store" });
  if (response.status === 401) throw new SignInRequired();
  if (!response.ok) throw new Error("Materials are not available right now. Please try again.");
  return response.json();
}
/*
 * Build the learner material download URL.
 */
export function materialDownload(id: string): string {
  return `/api/access/learner/materials/${encodeURIComponent(id)}/download`;
}
