/* Learners page route (US-003).
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */

import type { Metadata } from "next";
import LearnersScreen from "@/components/learners/learners-screen";

export const metadata: Metadata = { title: "Learners" };

export default function LearnersPage() {
  return <LearnersScreen />;
}
