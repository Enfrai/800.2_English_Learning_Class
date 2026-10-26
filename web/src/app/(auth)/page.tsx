/* Load standalone staff login with navigation to separate public pages.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

"use client";

import dynamic from "next/dynamic";
import PublicFrame from "@/components/club/public-frame";

const LoginForm = dynamic(() => import("@/components/login-form"), {
  ssr: false,
  loading: () => <main className="page" role="status">Loading sign in…</main>,
});

export default function Home() {
  return <PublicFrame><LoginForm /></PublicFrame>;
}
