/* One lesson route (US-006).
 * Author: Sandhya Tiwari
 * Date: 23 Oct 2026
 */

import type { Metadata } from "next";
import LessonScreen from "@/components/lessons/lesson-screen";

export const metadata: Metadata = { title: "Lesson" };

export default async function LessonPage({
  params,
}: {
  params: Promise<{ lessonId: string }>;
}) {
  const { lessonId } = await params;
  return <LessonScreen lessonId={lessonId} />;
}
