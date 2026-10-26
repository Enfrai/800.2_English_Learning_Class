"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { listLessons, listTags, LoginRequiredError, messageFor, type Lesson } from "@/lib/lessons-api";
import ReviewPill from "./review-pill";
import styles from "./lessons.module.css";

export default function LessonsScreen() {
  const router = useRouter();
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [topics, setTopics] = useState<string[]>([]);
  const [keyword, setKeyword] = useState("");
  const [tag, setTag] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tagError, setTagError] = useState("");
  const latest = useRef(0);
  useEffect(() => {
    let active = true;
    void listTags().then(rows => { if (active) { setTopics(rows.map(row => row.name)); setTagError(""); } }).catch(error => {
      if (!active) return;
      if (error instanceof LoginRequiredError) router.replace("/");
      else setTagError("Topic filters could not be loaded. Choose Refresh to try again.");
    });
    return () => { active = false; };
  }, [refresh, router]);
  useEffect(() => {
    const request = ++latest.current;
    setLoading(true); setError("");
    const timer = window.setTimeout(() => {
      void listLessons({ q: keyword, tag }).then(rows => {
        if (latest.current === request) setLessons(rows);
      }).catch(error => {
        if (latest.current !== request) return;
        if (error instanceof LoginRequiredError) router.replace("/");
        else setError(messageFor(error));
      }).finally(() => { if (latest.current === request) setLoading(false); });
    }, 250);
    return () => { window.clearTimeout(timer); if (latest.current === request) latest.current++; };
  }, [keyword, tag, refresh, router]);
  return <>
    <h1>Lessons</h1>
    <p className="sub">Keep lesson plans, topic tags and teaching materials together.</p>
    <div className={`row no-print ${styles.toolbar}`}>
      <Link href="/lessons/new" className="btn">New lesson</Link>
      <button className="btn btn-secondary" onClick={() => setRefresh(value => value + 1)}>Refresh</button>
    </div>
    <form className={`no-print ${styles.search}`} role="search" onSubmit={event => { event.preventDefault(); setRefresh(value => value + 1); }}>
      <div className="grid-2">
        <div className="field"><label htmlFor="lesson-search">Search lessons</label>
          <input id="lesson-search" type="search" maxLength={255} value={keyword} onChange={event => setKeyword(event.target.value)} aria-describedby="lesson-search-hint" />
          <p id="lesson-search-hint" className="hint">Search titles and topic tags. File contents are not searched.</p></div>
        <div className="field"><label htmlFor="lesson-topic">Topic tag</label>
          <select id="lesson-topic" value={tag} onChange={event => setTag(event.target.value)}>
            <option value="">All topics</option>{topics.map(topic => <option key={topic} value={topic}>{topic}</option>)}
          </select></div>
      </div>
      <div className="row"><button className="btn btn-secondary" type="submit">Search</button>
        <button className="btn btn-secondary" type="button" onClick={() => { setKeyword(""); setTag(""); }} disabled={!keyword && !tag}>Clear filters</button></div>
    </form>
    {tagError && <p className="msg msg-warning" role="status">{tagError}</p>}
    {loading && <p role="status">Searching lessons…</p>}
    {error && <div role="alert" className="msg msg-error">{error}</div>}
    {!loading && !error && <p role="status">{lessons.length ? `${lessons.length} lesson${lessons.length === 1 ? "" : "s"} found` : "No lessons found"}</p>}
    {!loading && !error && !lessons.length && <p className="msg msg-info"><Link href="/lessons/new">Create a new lesson</Link></p>}
    {!loading && !error && lessons.length > 0 && <div className={styles.table} role="region" aria-label="Lesson results" tabIndex={0}>
      <table className="data">
        <thead><tr><th scope="col">Title</th><th scope="col">Date</th><th scope="col">Topics</th><th scope="col">Materials</th><th scope="col" className="no-print">Actions</th></tr></thead>
        <tbody>{lessons.map(lesson => <tr key={lesson.id}>
          <td><Link href={`/lessons/${lesson.id}`}>{lesson.title}</Link>
            {lesson.review_label && <p><ReviewPill lesson={lesson} /></p>}</td>
          <td><time dateTime={lesson.lesson_date}>{lesson.lesson_date}</time></td>
          <td>{lesson.tags.map(topic => <span className="chip" key={topic}>{topic}</span>)}</td>
          <td>{lesson.materials.length}</td>
          <td className="no-print"><div className={styles.actions}>
            {lesson.can_edit ? <Link className="btn btn-secondary" href={`/lessons/${lesson.id}/edit`} aria-label={`Edit ${lesson.title}`}>Edit</Link> : <span>View only</span>}
            <Link className="btn btn-secondary" href={`/lessons/new?copyFrom=${lesson.id}`} aria-label={`Copy as new lesson: ${lesson.title}`}>Copy as new lesson</Link>
          </div></td>
        </tr>)}</tbody>
      </table>
    </div>}
  </>;
}
