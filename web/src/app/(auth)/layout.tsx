/* Define the authentication root layout and global feedback entry.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

import FeedbackEntry from "@/components/feedback/feedback-entry";
import type { Metadata } from "next";
import "@/styles/ako/tokens.css";
import "@/styles/ako/components.css";
import "./globals.css";

export const metadata: Metadata = {
  title: { template: "%s · Ako", default: "Ako" },
  description: "English Learning Class",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}<FeedbackEntry /></body>
    </html>
  );
}
