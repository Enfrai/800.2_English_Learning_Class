/* One lesson: its details, files to download, and Edit and Delete for the
 * author or a coordinator (UI design document 6.8, parts 4, 7 and 8).
 * Author: Sandhya Tiwari
 * Date: 23 Oct 2026
 * Updated: 24 Oct 2026 (open PDF and pictures in the browser, review label)
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { formatLessonDate, formatSize } from "./file-rule";
import ReviewLabel from "./review-label";
import {
  type Lesson,
  type Material,
  LoginRequiredError,
  NoPermissionError,
  NotFoundError,
  canOpenInBrowser,
  deleteLesson,
  downloadMaterial,
  getLesson,
  openMaterial,
  removeMaterial,
  setShareWithLearners,
} from "@/lib/lessons-api";

type LoadState = "loading" | "ready" | "login-required" | "not-found" | "failed";

// Message catalogue, UI design document section 7.
const NO_PERMISSION = "You do not have permission";
const LESSON_SAVED = "Lesson saved";
const ACTION_FAILED = "That did not work. Please try again.";
const DELETE_WARNING =
  "Delete this lesson? It leaves the lesson list and its files can no longer be downloaded.";

export default function LessonScreen({ lessonId }: { lessonId: string }) {
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setLesson(await getLesson(lessonId));
      setLoadState("ready");
    } catch (error) {
      if (error instanceof LoginRequiredError) setLoadState("login-required");
      else if (error instanceof NotFoundError) setLoadState("not-found");
      else setLoadState("failed");
    }
  }, [lessonId]);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("notice") === "saved") setNotice(LESSON_SAVED);
    void load();
  }, [load]);

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      await action();
    } catch (error) {
      if (error instanceof LoginRequiredError) setLoadState("login-required");
      else if (error instanceof NoPermissionError) setFailure(NO_PERMISSION);
      else if (error instanceof NotFoundError) setLoadState("not-found");
      else setFailure(ACTION_FAILED);
    } finally {
      setBusy(false);
    }
  }

  function confirmDelete() {
    void run(async () => {
      await deleteLesson(lessonId);
      window.location.assign("/lessons?notice=deleted");
    });
  }

  function changeShare(material: Material, share: boolean) {
    void run(async () => {
      const changed = await setShareWithLearners(material.id, share);
      setLesson((current) =>
        current && {
          ...current,
          materials: current.materials.map((item) => (item.id === changed.id ? changed : item)),
        },
      );
    });
  }

  function remove(material: Material) {
    void run(async () => {
      await removeMaterial(material.id);
      await load();
    });
  }

  if (loadState === "login-required") {
    return (
      <div className="msg msg-error" role="alert">
        Please log in to see this lesson. <a href="/">Log in</a>
      </div>
    );
  }
  if (loadState === "not-found") {
    return (
      <div className="msg msg-info" role="status">
        This lesson was not found. It may have been deleted. <a href="/lessons">Back to lessons</a>
      </div>
    );
  }
  if (loadState === "loading") return <p role="status">Loading lesson…</p>;
  if (loadState === "failed" || !lesson) {
    return (
      <div className="msg msg-error" role="alert">
        The lesson could not be loaded. Please try again.{" "}
        <button type="button" className="btn btn-secondary" onClick={() => void load()}>
          Try again
        </button>
      </div>
    );
  }

  return (
    <>
      <p className="no-print">
        <a href="/lessons">← All lessons</a>
      </p>
      <h1>{lesson.title}</h1>
      <p className="sub">{formatLessonDate(lesson.lesson_date)}</p>
      <ReviewLabel lesson={lesson} />
      <p>
        {lesson.tags.map((tag) => (
          <span key={tag} className="chip">
            {tag}
          </span>
        ))}
      </p>
      {notice && (
        <div className="msg msg-success" role="status">
          {notice}
        </div>
      )}

      {lesson.can_change && (
        <div className="row no-print">
          <a className="btn btn-secondary" href={`/lessons/${lesson.id}/edit`}>
            Edit lesson
          </a>
          <button type="button" className="btn btn-danger" onClick={() => setConfirmingDelete(true)}>
            Delete lesson
          </button>
        </div>
      )}
      {confirmingDelete && (
        <div className="msg msg-warning" role="alertdialog" aria-label="Confirm delete">
          {DELETE_WARNING}{" "}
          <div className="row" style={{ marginTop: "var(--space-2)" }}>
            <button type="button" className="btn btn-danger" onClick={confirmDelete}>
              Yes, delete
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmingDelete(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {failure && (
        <div className="msg msg-error" role="alert">
          {failure}
        </div>
      )}

      <h2>Files</h2>
      {lesson.materials.length === 0 ? (
        <div className="msg msg-info">No files attached.</div>
      ) : (
        <table className="data">
          <thead>
            <tr>
              <th scope="col">File</th>
              <th scope="col">Size</th>
              <th scope="col">Share with learners</th>
              <th scope="col" className="no-print">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {lesson.materials.map((material) => (
              <tr key={material.id}>
                <td>{material.file_name}</td>
                <td>{formatSize(material.file_size)}</td>
                <td>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={material.share_with_learners}
                      disabled={!lesson.can_change || busy}
                      aria-label={`Share ${material.file_name} with learners`}
                      onChange={(event) => changeShare(material, event.target.checked)}
                    />
                  </label>
                </td>
                <td className="no-print">
                  <div className="row">
                    {canOpenInBrowser(material) && (
                      <button
                        type="button"
                        className="btn btn-secondary"
                        aria-label={`Open ${material.file_name}`}
                        onClick={() => void run(() => openMaterial(material))}
                      >
                        Open
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-secondary"
                      aria-label={`Download ${material.file_name}`}
                      onClick={() => void run(() => downloadMaterial(material))}
                    >
                      Download
                    </button>
                    {lesson.can_change && (
                      <button
                        type="button"
                        className="btn btn-danger"
                        aria-label={`Remove ${material.file_name}`}
                        onClick={() => remove(material)}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
