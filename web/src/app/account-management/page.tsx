"use client";

import dynamic from "next/dynamic";
import SessionShell from "@/components/session-shell";

// Material Web uses browser APIs; preserve the project's client-only loading pattern.
const StaffManagement = dynamic(() => import("@/components/staff-management"), {
  ssr: false,
  loading: () => <p role="status">Loading account management…</p>,
});

/** Existing middleware and SessionShell enforce Coordinator access before mounting staff UI. */
export default function AccountManagement() {
  return <SessionShell><StaffManagement /></SessionShell>;
}
