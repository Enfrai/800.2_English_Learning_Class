/* Show a friendly missing-page screen and global feedback entry.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

import FeedbackEntry from "@/components/feedback/feedback-entry";
import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { PUBLIC_COPY as copy } from "@/lib/club-information";
import "@/styles/ako/tokens.css";
import "@/styles/ako/components.css";

export const viewport: Viewport = { width: "device-width", initialScale: 1 };
export const metadata: Metadata = { title: "Page not found · Ako" };
export default function GlobalNotFound() {
  return <html lang="en"><body>
    <header className="bar"><Link className="logo" href="/" aria-label="Ako home">Ako</Link></header>
    <main className="page"><h1>{copy.notFound}</h1><p>{copy.notFoundNote}</p>
      <Link className="btn" href="/">{copy.returnHome}</Link>
    </main>
  <FeedbackEntry /></body></html>;
}
