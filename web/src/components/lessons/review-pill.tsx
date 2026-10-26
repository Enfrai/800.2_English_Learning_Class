/* The Māori content review pill for the lesson list and page (UI design 6.10, US-008).
 * Author: Pei Wu
 * Date: 26 Oct 2026
 */

import type { Lesson } from "@/lib/lessons-api";

/** Amber "not yet reviewed", green "Reviewed by [name], [date]"; nothing for other lessons. */
export default function ReviewPill({ lesson }: { lesson: Pick<Lesson, "review_status" | "review_label"> }) {
  if (!lesson.review_label) return null;
  const reviewed = lesson.review_status === "reviewed";
  return <span className={`badge ${reviewed ? "badge-reviewed" : "badge-review"}`}>{lesson.review_label}</span>;
}
