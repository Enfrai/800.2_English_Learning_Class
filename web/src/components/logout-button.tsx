"use client";

import { FilledButton } from "./material";

export default function LogoutButton({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return <FilledButton disabled={disabled} onClick={onClick}>{disabled ? "Logging out…" : "Log out"}</FilledButton>;
}
