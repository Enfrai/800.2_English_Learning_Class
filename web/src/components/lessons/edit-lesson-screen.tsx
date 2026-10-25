/* Edit a lesson: loads it, then shows the form to the author or a coordinator.
 * Another teacher who types the address sees "You do not have permission"
 * (UI design document section 5).
 * Author: Sandhya Tiwari
 * Date: 23 Oct 2026
 */

"use client";

import { useEffect, useState } from "react";
import LessonForm from "./lesson-form";
import { type Lesson, LoginRequiredError, NotFoundError, getLesson } from "@/lib/lessons-api";

type LoadState = "loading" | "ready" | "login-required" | "not-found" | "failed";

export default function EditLessonScreen({ lessonId }: { lessonId: string }) {
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");

  useEffect(() => {
    getLesson(lessonId)
      .then((found) => {
        setLesson(found);
        setLoadState("ready");
      })
      .catch((error) => {
        if (error instanceof LoginRequiredError) setLoadState("login-required");
        else if (error instanceof NotFoundError) setLoadState("not-found");
        else setLoadState("failed");
      });
  }, [lessonId]);

  return (
    <>
      <h1>Edit lesson</h1>
      {loadState === "loading" && <p role="status">Loading lesson…</p>}
      {loadState === "login-required" && (
        <div className="msg msg-error" role="alert">
          Please log in to edit lessons. <a href="/">Log in</a>
        </div>
      )}
      {loadState === "not-found" && (
        <div className="msg msg-info" role="status">
          This lesson was not found. It may have been deleted. <a href="/lessons">Back to lessons</a>
        </div>
      )}
      {loadState === "failed" && (
        <div className="msg msg-error" role="alert">
          The lesson could not be loaded. Please try again.
        </div>
      )}
      {loadState === "ready" && lesson && !lesson.can_change && (
        <div className="msg msg-error" role="alert">
          You do not have permission
        </div>
      )}
      {loadState === "ready" && lesson?.can_change && <LessonForm lesson={lesson} />}
    </>
  );
}
