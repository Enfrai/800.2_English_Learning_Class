/* Validate feedback fields and submit same-origin requests without automatic retries.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

export type FeedbackInput = { title: string; email: string; description: string };
export class FeedbackError extends Error {}

export function validateFeedback(input: FeedbackInput): Partial<Record<keyof FeedbackInput, string>> {
  const errors: Partial<Record<keyof FeedbackInput, string>> = {};
  const title = input.title.trim(), email = input.email.trim(), description = input.description.trim();
  if (!title) errors.title = "Title is required";
  else if (Array.from(title).length > 200) errors.title = "Title must be 200 characters or fewer";
  else if (/[\x00-\x1f\x7f]/.test(title)) errors.title = "Title must not contain control characters";
  if (!email) errors.email = "Email is required";
  else {
    const parts = email.split("@"), local = parts[0] || "", domain = parts[1] || "";
    if (email.length > 254 || parts.length !== 2 || !/^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}$/.test(local)
      || local.startsWith(".") || local.endsWith(".") || local.includes("..") || !domain.includes(".")
      || !domain.split(".").every(label => /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label))) {
      errors.email = "Please enter a valid email address";
    }
  }
  if (!description) errors.description = "Description is required";
  else if (Array.from(description).length > 5000) errors.description = "Description must be 5,000 characters or fewer";
  else if (/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(description)) errors.description = "Description contains invalid characters";
  return errors;
}

export async function submitFeedback(input: FeedbackInput): Promise<string> {
  let response: Response;
  try {
    response = await fetch("/api/user/feedback", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: input.title.trim(), email: input.email.trim(), description: input.description.trim() }),
    });
  } catch {
    throw new FeedbackError("Unable to confirm delivery. Please try again later.");
  }
  if (response.status === 429) throw new FeedbackError("Too many feedback requests. Please wait before trying again.");
  if (response.status === 503) throw new FeedbackError("Feedback is temporarily unavailable. Please try again later.");
  if (response.status === 422) throw new FeedbackError("Please check the title, email and description.");
  if (!response.ok) throw new FeedbackError("Unable to confirm delivery. Please try again later.");
  const data: unknown = await response.json().catch(() => null);
  if (!data || typeof data !== "object" || !("message" in data)
    || data.message !== "Thank you. Your feedback has been submitted.") {
    throw new FeedbackError("Unable to confirm delivery. Please try again later.");
  }
  return data.message;
}
