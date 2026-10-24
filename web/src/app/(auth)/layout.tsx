/* Define the root layout and metadata for the login test application.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ELC Login",
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
