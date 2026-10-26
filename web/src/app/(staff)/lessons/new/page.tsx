import LessonEditor from "@/components/lessons/lesson-editor";

export const metadata = { title: "New lesson" };
export default async function Page({ searchParams }: { searchParams: Promise<{ copyFrom?: string | string[] }> }) {
  const params = await searchParams;
  return <LessonEditor copyFrom={typeof params.copyFrom === "string" ? params.copyFrom : undefined} />;
}
