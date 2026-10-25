import LessonEditor from "@/components/lessons/lesson-editor";

export const metadata = { title: "Edit lesson" };
export default async function Page({ params }: { params: Promise<{ lessonId: string }> }) {
  return <LessonEditor lessonId={(await params).lessonId} />;
}
