"use client";
import dynamic from "next/dynamic";
const LoginForm = dynamic(() => import("@/components/login-form"), {
  ssr: false, loading: () => <p role="status">Loading sign in…</p>,
});
export default function StaffLogin() { return <LoginForm embedded />; }
