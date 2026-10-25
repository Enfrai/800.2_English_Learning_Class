"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listLessons, LoginRequiredError, messageFor, type Lesson } from "@/lib/lessons-api";
import styles from "./lessons.module.css";

export default function LessonsScreen() {
  const router = useRouter();
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setLessons(await listLessons()); }
    catch (error) {
      if (error instanceof LoginRequiredError) router.replace("/");
      else setError(messageFor(error));
    } finally { setLoading(false); }
  }, [router]);
  useEffect(() => { void load(); }, [load]);
  return <>
    <h1>Lessons</h1>
    <p className="sub">Keep lesson plans, topic tags and teaching materials together.</p>
    <div className={`row no-print ${styles.toolbar}`}>
      <Link href="/lessons/new" className="btn">New lesson</Link>
      <button className="btn btn-secondary" onClick={() => void load()} disabled={loading}>Refresh</button>
    </div>
    {loading && <p role="status">Loading lessons…</p>}
    {error && <div role="alert" className="msg msg-error">{error}</div>}
    {!loading && !error && !lessons.length && <p className="msg msg-info">No lessons yet. Choose New lesson to start.</p>}
    {!loading && !error && lessons.length > 0 && <div className={styles.table}>
      <table className="data">
        <thead><tr><th scope="col">Title</th><th scope="col">Date</th><th scope="col">Topics</th><th scope="col">Materials</th><th scope="col" className="no-print">Actions</th></tr></thead>
        <tbody>{lessons.map(lesson => <tr key={lesson.id}>
          <td><Link href={`/lessons/${lesson.id}`}>{lesson.title}</Link>
            {lesson.review_label && <p><span className="badge badge-review">{lesson.review_label}</span></p>}</td>
          <td><time dateTime={lesson.lesson_date}>{lesson.lesson_date}</time></td>
          <td>{lesson.tags.map(tag => <span className="chip" key={tag}>{tag}</span>)}</td>
          <td>{lesson.materials.length}</td>
          <td className="no-print">{lesson.can_edit
            ? <Link className="btn btn-secondary" href={`/lessons/${lesson.id}/edit`} aria-label={`Edit ${lesson.title}`}>Edit</Link>
            : "View only"}</td>
        </tr>)}</tbody>
      </table>
    </div>}
  </>;
}
