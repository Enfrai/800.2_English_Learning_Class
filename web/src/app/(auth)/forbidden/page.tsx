import SessionShell from "@/components/session-shell";

export default function Forbidden() {
  return <SessionShell><p className="msg msg-error" role="alert">You do not have permission</p></SessionShell>;
}
