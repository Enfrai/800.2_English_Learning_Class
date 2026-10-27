/*
 * Validate sample club configuration before publishing approved schedule, contact or
 * greeting content.
 * Author: SandhyaCodes1
 * Date: 26 Oct 2026
 */

export type ClubInformation = {
  day: string; time: string; venue: string; address: string;
  sample: boolean;
  contact: { label: string; value: string; href: string };
  greeting: string | null;
};
export const SAMPLE_SCHEDULE = {
  day: "Monday", time: "10:00 am to 12:00 pm",
  venue: "Sample community room", address: "123 Example Street, Example Town",
};
export const PUBLIC_COPY = {
  title: "English classes",
  intro: "Find out when and where we meet.",
  sample: "These are sample details. Please confirm before visiting.",
  details: "Class information",
  day: "Class day", time: "Class time", venue: "Venue address", contact: "Contact",
  join: "How to join",
  walkIn: "You do not need to enrol before class.",
  noAccount: "Learners do not need an account.",
  enquiry: "Ask about classes", enquiryNote: "This form sends an enquiry. It does not enrol you.",
  staff: "Staff login", staffNote: "This login is for teachers and coordinators.",
  home: "Home", skip: "Skip to class information",
  notFound: "Page not found", notFoundNote: "We could not find that page.",
  returnHome: "Go to home page",
};
/*
 * Check whether the supplied value is a nonarray object record.
 */
const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
/*
 * Count words in trimmed public-information text.
 */
export function wordCount(value: string): number { return value.trim().split(/\s+/u).filter(Boolean).length; }
/*
 * Check whether public-information sentences meet the configured readability limit.
 */
export function shortSentences(value: string): boolean {
  return value.split(/[.!?]+(?:\s|$)/u).every(/*
     * Check whether every collection entry satisfies this validation rule.
     */
    sentence => wordCount(sentence) <= 15);
}
/*
 * Normalize and bound an optional public-information text value.
 */
function text(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim() || value.length > 250 || !shortSentences(value)) return null;
  return value.trim();
}
/*
 * Validate a calendar date used for approved public-information content.
 */
function validDay(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value + "T00:00:00Z");
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
/*
 * Validate club configuration and expose only approved public information.
 */
export function clubInformation(config: unknown, today = new Intl.DateTimeFormat("en-CA", { timeZone: "Pacific/Auckland", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date())): ClubInformation {
  const root = record(config), schedule = record(root.schedule), contact = record(root.contact), greeting = record(root.greeting);
  const values = [schedule.day, schedule.time, schedule.venue, schedule.address].map(text);
  const confirmed = schedule.confirmed === true && values.every(Boolean);
  const [day, time, venue, address] = confirmed ? values as string[] : Object.values(SAMPLE_SCHEDULE);
  let details = { label: "Enquiry form", value: "Send an enquiry", href: "/ask-about-classes" };
  if (contact.approved === true && typeof contact.value === "string") {
    const value = contact.value.trim();
    const parts = value.split("@"), local = parts[0] || "", domain = parts[1] || "";
    const email = parts.length === 2 && value.length <= 254 && local.length <= 64
      && /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local) && !local.startsWith(".")
      && !local.endsWith(".") && !local.includes("..") && domain.includes(".")
      && domain.split(".").every(/*
     * Check whether every collection entry satisfies this validation rule.
     */
    label => /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label));
    if (contact.type === "email" && email) {
      details = { label: "Email", value, href: "mailto:" + encodeURIComponent(local) + "@" + domain };
    } else if (contact.type === "phone" && /^\+?[0-9 ()-]+$/.test(value) && value.replace(/\D/g, "").length >= 7 && value.replace(/\D/g, "").length <= 15) {
      details = { label: "Phone", value, href: "tel:" + value.replace(/[ ()-]/g, "") };
    }
  }
  const reviewed = text(greeting.text) && typeof greeting.reviewer === "string" && greeting.reviewer.trim()
    && validDay(greeting.review_date) && greeting.review_date <= today;
  return { day, time, venue, address, sample: !confirmed, contact: details, greeting: reviewed ? text(greeting.text) : null };
}
