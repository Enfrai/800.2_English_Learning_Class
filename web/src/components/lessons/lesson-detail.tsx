"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { deleteLesson, deleteMaterial, getLesson, shareMaterial, materialUrl, LoginRequiredError, messageFor, type Lesson } from "@/lib/lessons-api";
import ReviewPill from "./review-pill";
import styles from "./lessons.module.css";

export default function LessonDetail({ lessonId }: { lessonId: string }) {
  const router = useRouter();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState<{ id: string; name: string; lesson: boolean } | null>(null);
  const handleError = useCallback((error: unknown) => {
    if (error instanceof LoginRequiredError) router.replace("/");
    else setError(messageFor(error));
  }, [router]);
  const load = useCallback(async () => {
    try { setLesson(await getLesson(lessonId)); }
    catch (error) { handleError(error); }
  }, [lessonId, handleError]);
  useEffect(() => { void load(); }, [load]);
  async function confirm() {
    if (!confirmation || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      if (confirmation.lesson) { await deleteLesson(lessonId); router.push("/lessons"); }
      else { await deleteMaterial(confirmation.id); setConfirmation(null); setNotice("Material removed"); await load(); }
    } catch (error) { handleError(error); }
    finally { setBusy(false); }
  }
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
    <p>{lesson.tags.map(tag => <span className="chip" key={tag}>{tag}</span>)}</p>
    {lesson.review_label && <p><ReviewPill lesson={lesson} /></p>}
    <p className={styles.description}>{lesson.description}</p>
    <div className="row no-print">
      <Link href="/lessons" className="btn btn-secondary">Back to lessons</Link>
      {lesson.can_edit && <>
        <Link href={`/lessons/${lesson.id}/edit`} className="btn">Edit lesson</Link>
        <button className="btn btn-danger" disabled={busy} onClick={() => setConfirmation({ id: lesson.id, name: lesson.title, lesson: true })}>Delete lesson</button>
      </>}
    </div>
    {error && <p className="msg msg-error" role="alert">{error}</p>}
    {notice && <p className="msg msg-success" role="status">{notice}</p>}
    {confirmation && <section className={`card no-print ${styles.confirmation}`} aria-labelledby="delete-heading">
      <h2 id="delete-heading">{confirmation.lesson ? "Delete lesson?" : "Remove material?"}</h2>
      <p>{confirmation.name}</p>
      <p>{confirmation.lesson ? "The lesson will leave the library. Its files will no longer be downloadable." : "This file will no longer be downloadable. Any existing Māori review will be reset."}</p>
      <div className="row">
        <button className="btn btn-danger" disabled={busy} onClick={() => void confirm()}>Confirm deletion</button>
        <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirmation(null)}>Cancel deletion</button>
      </div>
    </section>}
    <h2>Materials</h2>
    {!lesson.materials.length && <p className="msg msg-info">No materials attached yet.</p>}
    <ul className={styles.materials}>{lesson.materials.map(material => <li key={material.id} className={`card ${styles.material}`}>
      <p><a href={materialUrl(material.id)} download={material.file_name}>{material.file_name}</a></p>
      <p>{material.file_size.toLocaleString()} bytes · {material.share_with_learners ? "Selected for learner sharing" : "Staff only"}</p>
      {lesson.can_edit && <div className="no-print">
        <label className="check"><input type="checkbox" checked={material.share_with_learners} disabled={busy} onChange={e => void share(material.id, e.target.checked)} />Share {material.file_name} with learners</label>
        <button className="btn btn-danger" aria-label={"Remove " + material.file_name} disabled={busy} onClick={() => setConfirmation({ id: material.id, name: material.file_name, lesson: false })}>Remove file</button>
      </div>}
    </li>)}</ul>
  </>;
}
