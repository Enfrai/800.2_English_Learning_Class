/* Root layout for public phone pages (learners and visitors; no login).
 * Uses the Ako UI kit phone layout (docs/system_design/ako-ui-kit/layout-phone.html):
 * one column, 360 px wide, no staff menu and no session check.
 * Author: Pei Wu
 * Date: 25 Oct 2026
 */

import type { Metadata, Viewport } from "next";
import "@/styles/ako/tokens.css";
import "@/styles/ako/components.css";

export const metadata: Metadata = {
  title: { template: "%s · Ako", default: "Ako" },
  description: "English Learning Class",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

/*
 * Render the public layout interface and its associated content.
 */
export default function PublicLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        {/* A header (not the kit sample's div) so the bar sits in a landmark. */}
        <header className="phone-top">Ako</header>
        <main className="page-phone">{children}</main>
      </body>
    </html>
  );
}
