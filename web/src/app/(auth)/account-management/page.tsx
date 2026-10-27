/*
 * Render the Coordinator account-management route with its client-side staff editor.
 * Author: Enfrai
 * Date: 25 Oct 2026
 */

"use client";

import dynamic from "next/dynamic";
import SessionShell from "@/components/session-shell";

// Keep the existing loading state while loading account management.
const StaffManagement = dynamic(/*
     * Load the requested client component lazily.
     */
    () => import("@/components/staff-management"), {
  ssr: false,
  /*
   * Render the loading placeholder while the client component is imported.
   */
  loading: () => <p role="status">Loading account management…</p>,
});

/** Existing middleware and SessionShell enforce Coordinator access before mounting staff UI. */
export default function AccountManagement() {
  return <SessionShell><StaffManagement /></SessionShell>;
}
