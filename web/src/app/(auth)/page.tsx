/* Load standalone staff login with navigation to separate public pages.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

"use client";

import dynamic from "next/dynamic";
import PublicFrame from "@/components/club/public-frame";

const LoginForm = dynamic(/*
     * Load the requested client component lazily.
     */
    () => import("@/components/login-form"), {
  ssr: false,
  /*
   * Render the loading placeholder while the client component is imported.
   */
  loading: () => <main className="page" role="status">Loading sign in…</main>,
});

/*
 * Render the home interface and its associated content.
 */
export default function Home() {
  return <PublicFrame><LoginForm /></PublicFrame>;
}
