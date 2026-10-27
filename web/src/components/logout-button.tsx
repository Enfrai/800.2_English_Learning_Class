/*
 * Render the reusable logout control with its pending-operation state.
 * Author: Leonwu2026
 * Date: 24 Oct 2026
 */

"use client";

import { FilledButton } from "./material";

/*
 * Render the logout button interface and its associated content.
 */
export default function LogoutButton({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return <FilledButton disabled={disabled} onClick={onClick}>{disabled ? "Logging out…" : "Log out"}</FilledButton>;
}
