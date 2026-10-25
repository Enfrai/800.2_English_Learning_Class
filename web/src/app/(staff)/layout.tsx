/* Root layout for logged-in staff pages, styled with the Ako UI kit.
 * Authentication pages share the same Ako tokens and component styles.
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */

import type { Metadata } from "next";
import SessionShell from "@/components/session-shell";
import "@/styles/ako/tokens.css";
import "@/styles/ako/components.css";

export const metadata: Metadata = {
  title: { template: "%s · Ako", default: "Ako" },
  description: "English Learning Class",
};

export default function StaffLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <SessionShell layout="kit">{children}</SessionShell>
      </body>
    </html>
  );
}
