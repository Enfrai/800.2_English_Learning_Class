/* Edit a lesson route (US-006).
 * Author: Sandhya Tiwari
 * Date: 23 Oct 2026
 */

import type { Metadata } from "next";
import EditLessonScreen from "@/components/lessons/edit-lesson-screen";

export const metadata: Metadata = { title: "Edit lesson" };

export default async function EditLessonPage({
  params,
}: {
  params: Promise<{ lessonId: string }>;
}) {
  const { lessonId } = await params;
  return <EditLessonScreen lessonId={lessonId} />;
}
