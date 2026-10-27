/*
 * Render the selected lesson details and permitted material and review actions.
 * Author: collegelogin
 * Date: 24 Oct 2026
 */

import LessonDetail from "@/components/lessons/lesson-detail";

export const metadata = { title: "Lesson" };
/*
 * Render the lesson detail route.
 */
export default async function Page({ params }: { params: Promise<{ lessonId: string }> }) {
  return <LessonDetail lessonId={(await params).lessonId} />;
}
