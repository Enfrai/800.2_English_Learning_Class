/* Provide an accessible feedback entry on every application page.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

import Link from "next/link";
import styles from "./feedback.module.css";

export default function FeedbackEntry() {
  return <>
    <div className={styles.spacer} aria-hidden="true" />
    <Link className={styles.entry} href="/feedback" prefetch={false} aria-label="Send feedback" title="Send feedback">
      <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true" focusable="false">
        <path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 4v-4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
        <path d="M7 9h10M7 13h7" />
      </svg>
    </Link>
  </>;
}
