"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  getLesson, getCopyDraft, copyLesson, listTags, saveLesson, setMaoriContent, uploadMaterial, materialUrl,
  LoginRequiredError, LessonError, MAX_MATERIAL_BYTES, MATERIAL_RULE, messageFor,
  type Lesson, type CopyDraft,
} from "@/lib/lessons-api";
import styles from "./lessons.module.css";

type PendingFile = { id: number; file: File; share: boolean };
export default function LessonEditor({ lessonId, copyFrom }: { lessonId?: string; copyFrom?: string }) {
  const router = useRouter();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [draft, setDraft] = useState<CopyDraft | null>(null);
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [topics, setTopics] = useState("");
  const [description, setDescription] = useState("");
  const [maoriContent, setMaoriContentTicked] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [files, setFiles] = useState<PendingFile[]>([]);
  const [loading, setLoading] = useState(Boolean(lessonId || copyFrom));
  const [loadError, setLoadError] = useState("");
  const [message, setMessage] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const nextFile = useRef(0);
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    let active = true;
    void listTags().then(rows => { if (active) setSuggestions(rows.map(row => row.name)); }).catch(() => {});
    if (copyFrom && !lessonId) void getCopyDraft(copyFrom).then(row => {
      if (!active) return;
      setDraft(row); setTitle(row.title); setDate("");
      setTopics(row.tags.join(", ")); setDescription(row.description);
      // US-008: a copy keeps the flag (its review starts again). Without this
      // the unticked box would remove the flag from the copy when it is saved.
      setMaoriContentTicked(row.has_maori_content);
    }).catch(error => {
      if (!active) return;
      if (error instanceof LoginRequiredError) router.replace("/");
      else setLoadError(messageFor(error));
    }).finally(() => { if (active) setLoading(false); });
    if (lessonId) void getLesson(lessonId).then(row => {
      if (!active) return;
      setLesson(row); setTitle(row.title); setDate(row.lesson_date);
      setTopics(row.tags.join(", ")); setDescription(row.description || "");
      setMaoriContentTicked(row.has_maori_content);
    }).catch(error => {
      if (!active) return;
      if (error instanceof LoginRequiredError) router.replace("/");
      else setLoadError(messageFor(error));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [lessonId, copyFrom, router]);
  function focusError(errors: Record<string, string>) {
    setFields(errors);
    form.current?.querySelector<HTMLElement>(`[name="${Object.keys(errors)[0]}"]`)?.focus();
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    const tags = [...new Set(topics.split(",").map(tag => tag.trim()).filter(Boolean))];
    const errors: Record<string, string> = {};
    if (!title.trim()) errors.title = "Title is required";
    else if (Array.from(title.trim()).length > 255) errors.title = "Title must be 255 characters or fewer";
    if (!date) errors.lesson_date = "Lesson date is required";
    if (!tags.length) errors.tags = "At least one topic tag is required";
    else if (tags.some(tag => Array.from(tag).length > 100)) errors.tags = "Each topic tag must be 100 characters or fewer";
    if (files.some(item => item.file.size > MAX_MATERIAL_BYTES || !/\.(pdf|docx|jpe?g|png)$/i.test(item.file.name))) errors.materials = MATERIAL_RULE;
    setMessage(""); focusError(errors);
    if (Object.keys(errors).length) return;
    pending.current = true; setBusy(true);
    try {
      const input = { title, lesson_date: date, tags, description };
      const saved = copyFrom && !lesson
        ? await copyLesson(copyFrom, input, (draft?.materials || []).map(item => item.id))
        : await saveLesson(lessonId || lesson?.id || null, input);
      setLesson(saved);
      // US-008: the flag has its own endpoint; it is only called when the tick changed.
      if (saved.has_maori_content !== maoriContent) {
        try {
          await setMaoriContent(saved.id, maoriContent);
          setLesson({ ...saved, has_maori_content: maoriContent });
        } catch (error) {
          if (error instanceof LoginRequiredError) { router.replace("/"); return; }
          setMessage("Lesson details saved. Contains Māori content could not be saved. " + messageFor(error));
          return;
        }
      }
      for (const item of files) {
        try {
          const material = await uploadMaterial(saved.id, item.file, item.share);
          setLesson(current => current ? { ...current, materials: [...current.materials, material] } : current);
          setFiles(current => current.filter(file => file.id !== item.id));
        } catch (error) {
          if (error instanceof LoginRequiredError) { router.replace("/"); return; }
          setMessage("Lesson details saved. Some uploads could not be confirmed. " + messageFor(error));
          return;
        }
      }
      router.push(`/lessons/${saved.id}`);
    } catch (error) {
      if (error instanceof LoginRequiredError) router.replace("/");
      else {
        setMessage(messageFor(error));
        if (error instanceof LessonError) setFields(error.fields);
      }
    } finally { pending.current = false; setBusy(false); }
  }
  const fieldError = (name: string) => fields[name] && <p id={`${name}-error`} className="msg msg-error" role="alert">{fields[name]}</p>;
  const attrs = (name: string) => ({ "aria-invalid": Boolean(fields[name]), "aria-describedby": fields[name] ? `${name}-error` : undefined });
  if (loading) return <p role="status">Loading lesson…</p>;
  if (loadError) return <><h1>Lesson</h1><p className="msg msg-error" role="alert">{loadError}</p><Link href="/lessons">Back to lessons</Link></>;
  if (lessonId && lesson && !lesson.can_edit) return <><h1>Edit lesson</h1><p className="msg msg-error" role="alert">You do not have permission</p><Link href={`/lessons/${lessonId}`}>View lesson</Link></>;
  return <>
    <h1>{lessonId ? "Edit lesson" : copyFrom ? "Copy lesson" : "New lesson"}</h1>
    <p className="sub">Save the lesson date, topics and materials for other volunteers.</p>
    {copyFrom && !lesson && <p className="msg msg-info">This is an unsaved copy. Choose a date before saving. The original stays unchanged.</p>}
    {draft?.has_maori_content && !lesson && <p className="msg msg-warning">This copy contains Māori content and will need a new review.</p>}
    <form className={styles.form} ref={form} onSubmit={save} noValidate aria-busy={busy}>
      <div className="field"><label htmlFor="title" className="req">Title</label>
        <input id="title" name="title" type="text" required value={title} disabled={busy} {...attrs("title")} onChange={e => setTitle(e.target.value)} />
        {fieldError("title")}</div>
      <div className="grid-2">
        <div className="field"><label htmlFor="lesson-date" className="req">Lesson date</label>
          <input id="lesson-date" name="lesson_date" type="date" required value={date} disabled={busy} {...attrs("lesson_date")} onChange={e => setDate(e.target.value)} />
          {fieldError("lesson_date")}</div>
        <div className="field"><label htmlFor="topics" className="req">Topic tags</label>
          <input id="topics" name="tags" type="text" required value={topics} disabled={busy} {...attrs("tags")} onChange={e => setTopics(e.target.value)} />
          <p className="hint">Separate topics with commas, for example transport, health, shopping.</p>
          {suggestions.length > 0 && <p className="hint">Existing topics: {suggestions.join(", ")}</p>}
          {fieldError("tags")}</div>
      </div>
      <div className="field">
        <label className="check"><input type="checkbox" name="has_maori_content" checked={maoriContent} disabled={busy}
          aria-describedby="maori-content-hint" onChange={e => setMaoriContentTicked(e.target.checked)} />Contains Māori content</label>
        <p id="maori-content-hint" className="hint">
          Adds the label &quot;Māori content – not yet reviewed&quot; until a coordinator records a review.
          {lesson?.review_status === "reviewed" && " Unticking removes the recorded review."}
        </p></div>
      <div className="field"><label htmlFor="description">Teaching notes (optional)</label>
        <textarea id="description" value={description} disabled={busy} onChange={e => setDescription(e.target.value)} /></div>
      <h2>Materials</h2>
      <p className="sub">{MATERIAL_RULE}. Files are private to staff unless selected for later learner sharing.</p>
      {draft && !lesson && <>
        <p className="hint">Copied files are staff only. You can change sharing after saving.</p>
        <ul className={styles.materials}>{draft.materials.map(material => <li className={`card ${styles.material}`} key={material.id}>
          <p><a href={materialUrl(material.id)} download>{material.file_name}</a></p>
          <button className="btn btn-secondary" type="button" disabled={busy} aria-label={"Remove copied " + material.file_name}
            onClick={() => setDraft(current => current ? { ...current, materials: current.materials.filter(item => item.id !== material.id) } : current)}>Remove from copy</button>
        </li>)}</ul>
      </>}
      {lesson && lesson.materials.length > 0 && <ul>{lesson.materials.map(material =>
        <li key={material.id}><a href={materialUrl(material.id)} download>{material.file_name}</a></li>)}</ul>}
      <div className="field"><label htmlFor="materials">Add materials (optional)</label>
        <input className={styles.file} id="materials" name="materials" type="file" multiple accept=".pdf,.docx,.jpg,.jpeg,.png" disabled={busy}
          {...attrs("materials")} onChange={e => {
            const selected = Array.from(e.target.files || []).map(file => ({ id: nextFile.current++, file, share: false }));
            setFiles(current => [...current, ...selected]); e.target.value = "";
          }} />
        {fieldError("materials")}</div>
      <ul className={styles.materials}>{files.map(item => <li className={`card ${styles.material}`} key={item.id}>
        <p>{item.file.name} ({item.file.size.toLocaleString()} bytes)</p>
        <label className="check"><input type="checkbox" checked={item.share} disabled={busy} onChange={e => setFiles(current => current.map(file => file.id === item.id ? { ...file, share: e.target.checked } : file))} />
          Share {item.file.name} with learners</label>
        <button className="btn btn-secondary" aria-label={"Remove " + item.file.name} type="button" disabled={busy} onClick={() => setFiles(current => current.filter(file => file.id !== item.id))}>Remove file</button>
      </li>)}</ul>
      <div className="row no-print">
        <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save lesson"}</button>
        {!busy && <Link className="btn btn-secondary" href={lesson ? `/lessons/${lesson.id}` : copyFrom ? `/lessons/${copyFrom}` : "/lessons"}>Cancel</Link>}
      </div>
      {busy && <p role="status">Saving lesson and materials…</p>}
      {message && <p className="msg msg-error" role="alert">{message}</p>}
    </form>
  </>;
}
