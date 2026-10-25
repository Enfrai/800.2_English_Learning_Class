/* Date wording shared by staff and learner pages.
 * Author: Pei Wu
 * Date: 25 Oct 2026
 */

/** "2026-10-25" -> "Sunday, 25 October 2026", without a time-zone shift. */
export function formatSessionDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-NZ", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}
