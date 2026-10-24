/* Root layout for logged-in staff pages, styled with the Ako UI kit.
 * The login page has its own root layout in (auth), so the two style sheets
 * never load on the same page.
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */

import type { Metadata } from "next";
import MenuBar from "@/components/menu-bar";
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
        <MenuBar />
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
