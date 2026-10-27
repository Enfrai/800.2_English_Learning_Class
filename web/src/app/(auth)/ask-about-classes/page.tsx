/*
 * Render the public class-enquiry page separately from staff login.
 * Author: Enfrai
 * Date: 26 Oct 2026
 */

import PublicFrame from "@/components/club/public-frame";
import EnquiryEntry from "@/components/club/enquiry-entry";
import styles from "@/components/club/club-home.module.css";
export const metadata = { title: "Ask about classes" };
/*
 * Render the ask about classes page interface and its associated content.
 */
export default function AskAboutClassesPage() {
  return <PublicFrame><main className={`page ${styles.home} ${styles.main}`}>
    <h1>Ask about classes</h1>
    <p>This form sends an enquiry. It does not enrol you.</p>
    <section className={styles.enquiries} aria-label="Class enquiry"><EnquiryEntry />
      <noscript><p>Turn on JavaScript to send an enquiry.</p></noscript>
    </section>
  </main></PublicFrame>;
}
