/* Add a lesson route (US-006).
 * Author: Sandhya Tiwari
 * Date: 23 Oct 2026
 */

import type { Metadata } from "next";
import LessonForm from "@/components/lessons/lesson-form";

export const metadata: Metadata = { title: "Add lesson" };

export default function NewLessonPage() {
  return (
    <>
      <h1>Add lesson</h1>
      <p className="sub">Keep the lesson, its topic tags and its files in one place.</p>
      <LessonForm lesson={null} />
    </>
  );
}
