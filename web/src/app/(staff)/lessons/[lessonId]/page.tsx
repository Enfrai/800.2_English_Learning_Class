import LessonDetail from "@/components/lessons/lesson-detail";

export const metadata = { title: "Lesson" };
export default async function Page({ params }: { params: Promise<{ lessonId: string }> }) {
  return <LessonDetail lessonId={(await params).lessonId} />;
}
