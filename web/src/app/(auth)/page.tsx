/* Load the Ako login screen with a client-side loading state.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

"use client";

import dynamic from "next/dynamic";

const LoginForm = dynamic(() => import("@/components/login-form"), {
  ssr: false,
  loading: () => <main className="page" role="status">Loading sign in…</main>,
});

export default function Home() {
  return <LoginForm />;
}
