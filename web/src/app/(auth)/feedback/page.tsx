/* Expose the public feedback form using the shared Ako page layout.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

import PublicFrame from "@/components/club/public-frame";
import FeedbackForm from "@/components/feedback/feedback-form";

export const metadata = { title: "Feedback" };

export default function FeedbackPage() {
  return <PublicFrame><main className="page">
    <h1>Feedback</h1>
    <p>Tell us about a problem or suggest an improvement.</p>
    <FeedbackForm />
    <noscript><p>Turn on JavaScript to submit feedback.</p></noscript>
  </main></PublicFrame>;
}
