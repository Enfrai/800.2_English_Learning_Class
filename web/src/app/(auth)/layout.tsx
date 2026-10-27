/* Define the root layout and metadata for the login test application.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

import type { Metadata } from "next";
import "@/styles/ako/tokens.css";
import "@/styles/ako/components.css";
import "./globals.css";

export const metadata: Metadata = {
  title: { template: "%s · Ako", default: "Ako" },
  description: "English Learning Class",
};

/*
 * Render the root layout interface and its associated content.
 */
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
