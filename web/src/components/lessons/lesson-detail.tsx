/*
 * Display lesson metadata, attachments, sharing controls and review state.
 * Author: SandhyaCodes1
 * Date: 26 Oct 2026
 */

"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { deleteLesson, deleteMaterial, getLesson, shareMaterial, materialUrl, LoginRequiredError, messageFor, type Lesson } from "@/lib/lessons-api";
import { useSession } from "@/components/session-context";
import ReviewForm from "./review-form";
import ReviewPill from "./review-pill";
import styles from "./lessons.module.css";

/*
 * Render the lesson detail interface and its associated content.
 */
export default function LessonDetail({ lessonId }: { lessonId: string }) {
  const router = useRouter();
  // The Lesson service decides who may review; the role only chooses what to show.
  const isCoordinator = useSession()?.role === "coordinator";
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState<{ id: string; name: string; lesson: boolean } | null>(null);
  const handleError = useCallback(/*
     * Run the memoized handle error operation for the current dependencies.
     */
    (error: unknown) => {
    if (error instanceof LoginRequiredError) router.replace("/");
    else setError(messageFor(error));
  }, [router]);
  const load = useCallback(/*
     * Run the memoized load operation for the current dependencies.
     */
    async () => {
    try { setLesson(await getLesson(lessonId)); }
    catch (error) { handleError(error); }
  }, [lessonId, handleError]);
  useEffect(/*
     * Synchronize the component with its current dependencies and manage effect
     * resources.
     */
    () => { void load(); }, [load]);
  /*
   * Apply the confirmed lesson or material action and update the current view.
   */
  async function confirm() {
    if (!confirmation || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      if (confirmation.lesson) { await deleteLesson(lessonId); router.push("/lessons"); }
      else { await deleteMaterial(confirmation.id); setConfirmation(null); setNotice("Material removed"); await load(); }
    } catch (error) { handleError(error); }
    finally { setBusy(false); }
  }
  /*
   * Update the learner-sharing state of the selected material.
   */
  async function share(id: string, checked: boolean) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await shareMaterial(id, checked); await load(); setNotice("Sharing preference saved"); }
    catch (error) { handleError(error); }
    finally { setBusy(false); }
  }
  if (!lesson) return <><h1>Lesson</h1>{error ? <p className="msg msg-error" role="alert">{error}</p> : <p role="status">Loading lesson…</p>}<Link href="/lessons">Back to lessons</Link></>;
  return <>
    <h1 className={styles.heading}>{lesson.title}</h1>
    <p className="sub">Lesson date: <time dateTime={lesson.lesson_date}>{lesson.lesson_date}</time></p>
    <p>{lesson.tags.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    tag => <span className="chip" key={tag}>{tag}</span>)}</p>
    {lesson.review_label && <p><ReviewPill lesson={lesson} /></p>}
    {isCoordinator && lesson.has_maori_content && <ReviewForm lessonId={lesson.id}
      onSaved={/*
     * Handle the saved event for this control.
     */
    async () => { setError(""); await load(); setNotice("Review saved"); }}
      onLoginRequired={/*
     * Handle the login required event for this control.
     */
    () => router.replace("/")} />}
    <p className={styles.description}>{lesson.description}</p>
    <div className="row no-print">
      <Link href="/lessons" className="btn btn-secondary">Back to lessons</Link>
      <Link href={`/lessons/new?copyFrom=${lesson.id}`} className="btn btn-secondary">Copy as new lesson</Link>
      {lesson.can_edit && <>
        <Link href={`/lessons/${lesson.id}/edit`} className="btn">Edit lesson</Link>
        <button className="btn btn-danger" disabled={busy} onClick={/*
     * Handle the click event for this control.
     */
    () => setConfirmation({ id: lesson.id, name: lesson.title, lesson: true })}>Delete lesson</button>
      </>}
    </div>
    {error && <p className="msg msg-error" role="alert">{error}</p>}
    {notice && <p className="msg msg-success" role="status">{notice}</p>}
    {confirmation && <section className={`card no-print ${styles.confirmation}`} aria-labelledby="delete-heading">
      <h2 id="delete-heading">{confirmation.lesson ? "Delete lesson?" : "Remove material?"}</h2>
      <p>{confirmation.name}</p>
      <p>{confirmation.lesson ? "The lesson will leave the library. Its files will no longer be downloadable." : "This file will no longer be downloadable. Any existing Māori review will be reset."}</p>
      <div className="row">
        <button className="btn btn-danger" disabled={busy} onClick={/*
     * Handle the click event for this control.
     */
    () => void confirm()}>Confirm deletion</button>
        <button className="btn btn-secondary" disabled={busy} onClick={/*
     * Handle the click event for this control.
     */
    () => setConfirmation(null)}>Cancel deletion</button>
      </div>
    </section>}
    <h2>Materials</h2>
    {!lesson.materials.length && <p className="msg msg-info">No materials attached yet.</p>}
    <ul className={styles.materials}>{lesson.materials.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    material => <li key={material.id} className={`card ${styles.material}`}>
      <p><a href={materialUrl(material.id)} download={material.file_name}>{material.file_name}</a></p>
      <p>{material.file_size.toLocaleString()} bytes · {material.share_with_learners ? "Selected for learner sharing" : "Staff only"}</p>
      {lesson.can_edit && <div className="no-print">
        <label className="check"><input type="checkbox" checked={material.share_with_learners} disabled={busy} onChange={/*
     * Handle the change event for this control.
     */
    e => void share(material.id, e.target.checked)} />Share {material.file_name} with learners</label>
        <button className="btn btn-danger" aria-label={"Remove " + material.file_name} disabled={busy} onClick={/*
     * Handle the click event for this control.
     */
    () => setConfirmation({ id: material.id, name: material.file_name, lesson: false })}>Remove file</button>
      </div>}
    </li>)}</ul>
  </>;
}
