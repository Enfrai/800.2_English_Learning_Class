/*
 * Render the existing-lesson editor for the route lesson identifier.
 * Author: collegelogin
 * Date: 24 Oct 2026
 */

import LessonEditor from "@/components/lessons/lesson-editor";

export const metadata = { title: "Edit lesson" };
/*
 * Render the existing lesson editor route.
 */
export default async function Page({ params }: { params: Promise<{ lessonId: string }> }) {
  return <LessonEditor lessonId={(await params).lessonId} />;
}
