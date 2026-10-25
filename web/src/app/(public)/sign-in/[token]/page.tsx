/* Learner QR sign-in page route (US-012).
 * Author: Pei Wu
 * Date: 25 Oct 2026
 */

import type { Metadata } from "next";
import SignInScreen from "@/components/sign-in/sign-in-screen";

export const metadata: Metadata = {
  title: "Sign in",
  // The address holds the check-in token: keep it out of search engines and
  // never send it to another site.
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default async function SignInPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <SignInScreen token={token} />;
}
