/* Navy menu bar shown on every logged-in page (UI design document section 4).
 * Author: Pei Wu
 * Date: 23 Oct 2026
 * Updated: Sandhya Tiwari, 24 Oct 2026 (log out ends the session on the server)
 */

"use client";

import { usePathname } from "next/navigation";
import { clearSessionId } from "@/lib/session";

// Items that both teachers and coordinators may use. Coordinator-only items
// (Attendance reports, Accounts) are added once the login returns the role.
const MENU_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/sessions", label: "Class sessions" },
  { href: "/learners", label: "Learners" },
  { href: "/lessons", label: "Lessons" },
];

export default function MenuBar() {
  const pathname = usePathname();

  async function logOut() {
    const response = await fetch("/api/user/logout", {
      method: "POST", credentials: "same-origin", cache: "no-store",
    });
    if (!response.ok && response.status !== 401) return;
    clearSessionId();
    window.location.assign("/");
  }

  return (
    <header className="bar">
      <a className="logo" href="/">
        Ako
      </a>
      <nav aria-label="Main">
        {MENU_ITEMS.map((item) => (
          <a
            key={item.href}
            href={item.href}
            // A section stays current on its sub-pages, e.g. a session's attendance.
            aria-current={
              (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href))
                ? "page"
                : undefined
            }
          >
            {item.label}
          </a>
        ))}
      </nav>
      <div className="who">
        <a
          href="/"
          onClick={(event) => {
            event.preventDefault();
            void logOut();
          }}
        >
          Log out
        </a>
      </div>
    </header>
  );
}
