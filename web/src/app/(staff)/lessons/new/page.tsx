/*
 * Render the lesson creation or source-copy editor.
 * Author: collegelogin
 * Date: 24 Oct 2026
 */

import LessonEditor from "@/components/lessons/lesson-editor";

export const metadata = { title: "New lesson" };
/*
 * Render the new lesson editor route.
 */
export default async function Page({ searchParams }: { searchParams: Promise<{ copyFrom?: string | string[] }> }) {
  const params = await searchParams;
  return <LessonEditor copyFrom={typeof params.copyFrom === "string" ? params.copyFrom : undefined} />;
}
