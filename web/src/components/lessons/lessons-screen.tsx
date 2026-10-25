/* Lessons page: the shared list of lessons (UI design document 6.8 and 6.9).
 * Every logged-in teacher and coordinator sees every lesson, because lessons
 * are shared. Edit shows only for the author or a coordinator.
 * Author: Sandhya Tiwari
 * Date: 23 Oct 2026
 * Updated: 24 Oct 2026 (file count and Māori content review label)
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { formatLessonDate } from "./file-rule";
import ReviewLabel from "./review-label";
import { type LessonSummary, LoginRequiredError, listLessons } from "@/lib/lessons-api";

type LoadState = "loading" | "ready" | "login-required" | "failed";

// Message catalogue, UI design document section 7.
const NO_LESSONS = "No lessons found";
const NOTICES: Record<string, string> = {
  saved: "Lesson saved",
  deleted: "Lesson deleted",
};

export default function LessonsScreen() {
  const [lessons, setLessons] = useState<LessonSummary[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLessons(await listLessons());
      setLoadState("ready");
    } catch (error) {
      setLoadState(error instanceof LoginRequiredError ? "login-required" : "failed");
    }
  }, []);

  useEffect(() => {
    // The lesson and edit pages come back here with ?notice=saved or ?notice=deleted.
    const key = new URLSearchParams(window.location.search).get("notice");
    if (key && NOTICES[key]) setNotice(NOTICES[key]);
    void load();
  }, [load]);

  if (loadState === "login-required") {
    return (
      <>
        <h1>Lessons</h1>
        <div className="msg msg-error" role="alert">
          Please log in to see the lessons. <a href="/">Log in</a>
        </div>
      </>
    );
  }

  return (
    <>
      <h1>Lessons</h1>
      <p className="sub">Lessons are shared, so every teacher can find and reuse them.</p>

      <div className="row no-print" style={{ marginBottom: "var(--space-4)" }}>
        <a className="btn" href="/lessons/new">
          Add lesson
        </a>
      </div>
      {notice && (
        <div className="msg msg-success" role="status">
          {notice}
        </div>
      )}

      {loadState === "loading" && <p role="status">Loading lessons…</p>}
      {loadState === "failed" && (
        <div className="msg msg-error" role="alert">
          The lessons could not be loaded. Please try again.{" "}
          <button type="button" className="btn btn-secondary" onClick={() => void load()}>
            Try again
          </button>
        </div>
      )}
      {loadState === "ready" && lessons.length === 0 && (
        <div className="msg msg-info">
          {NO_LESSONS}. <a href="/lessons/new">Add a lesson</a>
        </div>
      )}
      {loadState === "ready" && lessons.length > 0 && <LessonTable lessons={lessons} />}
    </>
  );
}

function LessonTable({ lessons }: { lessons: LessonSummary[] }) {
  return (
    <table className="data">
      <thead>
        <tr>
          <th scope="col">Title</th>
          <th scope="col">Date</th>
          <th scope="col">Topic tags</th>
          <th scope="col">Files</th>
          <th scope="col" className="no-print">
            Actions
          </th>
        </tr>
      </thead>
      <tbody>
        {lessons.map((lesson) => (
          <tr key={lesson.id}>
            <td>
              <a href={`/lessons/${lesson.id}`}>{lesson.title}</a> <ReviewLabel lesson={lesson} />
            </td>
            <td>{formatLessonDate(lesson.lesson_date)}</td>
            <td>
              {lesson.tags.map((tag) => (
                <span key={tag} className="chip">
                  {tag}
                </span>
              ))}
            </td>
            <td>{lesson.material_count}</td>
            <td className="no-print">
              <div className="row">
                <a className="btn btn-secondary" href={`/lessons/${lesson.id}`} aria-label={`Open ${lesson.title}`}>
                  Open
                </a>
                {lesson.can_change && (
                  <a
                    className="btn btn-secondary"
                    href={`/lessons/${lesson.id}/edit`}
                    aria-label={`Edit ${lesson.title}`}
                  >
                    Edit
                  </a>
                )}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
