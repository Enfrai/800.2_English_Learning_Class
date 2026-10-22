/* Navy menu bar shown on every logged-in page (UI design document section 4).
 * Author: Pei Wu
 * Date: 23 Oct 2026
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

  function logOut() {
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
            aria-current={pathname === item.href ? "page" : undefined}
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
            logOut();
          }}
        >
          Log out
        </a>
      </div>
    </header>
  );
}
