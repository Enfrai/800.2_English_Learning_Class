/* Lessons list route (US-006).
 * Author: Sandhya Tiwari
 * Date: 23 Oct 2026
 */

import type { Metadata } from "next";
import LessonsScreen from "@/components/lessons/lessons-screen";

export const metadata: Metadata = { title: "Lessons" };

export default function LessonsPage() {
  return <LessonsScreen />;
}
