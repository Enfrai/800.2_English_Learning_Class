/* "Māori content – not yet reviewed" label (UI design document 6.10, US-008).
 * Shown on the lesson list and the lesson page while a lesson with Māori
 * content has no recorded review.
 * Author: Sandhya Tiwari
 * Date: 24 Oct 2026
 */

import type { LessonSummary } from "@/lib/lessons-api";

// Message catalogue, UI design document section 7.
const NOT_YET_REVIEWED = "Māori content – not yet reviewed";
const REVIEWED = "Māori content – reviewed";

export default function ReviewLabel({ lesson }: { lesson: LessonSummary }) {
  if (!lesson.has_maori_content) return null;
  if (lesson.review_status === "reviewed") {
    return <span className="badge badge-reviewed">{REVIEWED}</span>;
  }
  return <span className="badge badge-review">{NOT_YET_REVIEWED}</span>;
}
