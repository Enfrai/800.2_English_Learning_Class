/* Define shared root styles and metadata for public information and staff login.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

import type { Metadata, Viewport } from "next";
import "@/styles/ako/tokens.css";
import "@/styles/ako/components.css";
import "./globals.css";

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export const metadata: Metadata = {
  title: { template: "%s · Ako", default: "Ako" },
  description: "English Learning Class",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
