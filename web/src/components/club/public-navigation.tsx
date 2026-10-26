"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./club-home.module.css";
const links = [
  { href: "/class-information", label: "Class information" },
  { href: "/ask-about-classes", label: "Ask about classes" },
  { href: "/", label: "Staff login" },
];
export default function PublicNavigation() {
  const pathname = usePathname();
  return <header className={`bar ${styles.header}`}>
    <Link className="logo" href="/" aria-label="Ako home">Ako</Link>
    <nav aria-label="Public menu">{links.map(link => <Link key={link.href} href={link.href}
      aria-current={pathname === link.href ? "page" : undefined}>{link.label}</Link>)}</nav>
  </header>;
}
