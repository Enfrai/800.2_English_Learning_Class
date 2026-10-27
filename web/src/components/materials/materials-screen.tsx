/*
 * Display learner-shared class materials and handle missing or expired access grants.
 * Author: SandhyaCodes1
 * Date: 26 Oct 2026
 */

"use client";
import { useEffect, useState } from "react";
import { getMaterials, materialDownload, SignInRequired, type Materials } from "@/lib/materials-api";
import { formatSessionDate } from "@/lib/dates";
import styles from "./materials.module.css";
/*
 * Render the materials screen interface and its associated content.
 */
export default function MaterialsScreen({ embedded = false }: { embedded?: boolean }) {
  const [data, setData] = useState<Materials | null>(null);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(/*
     * Synchronize the component with its current dependencies and manage effect
     * resources.
     */
    () => {
    let active = true;
    setError(""); setData(null);
    /*
     * Load the current shared materials and update the loading or error state.
     */
    const load = () => getMaterials().then(/*
     * Apply the completed asynchronous result to the component’s data or state.
     */
    value => { if (active) setData(value); }).catch(/*
     * Handle an asynchronous failure using the workflow’s error state.
     */
    reason => {
      if (!active) return;
      if (reason instanceof SignInRequired) { setData(null); setExpired(true); }
      else setError("Materials are not available right now. Please try again.");
    });
    void load();
    const timer = window.setInterval(/*
     * Compute the next interval state from its previous value.
     */
    () => void load(), 60000);
    /*
     * Release resources installed by the enclosing component effect.
     */
    return () => { active = false; window.clearInterval(timer); };
  }, [attempt]);
  return <>
    {embedded ? <h2>Lesson materials</h2> : <h1>Lesson materials</h1>}
    {expired ? <div role="status"><p>Please scan a class code and sign in again.</p><a className="btn" href="/sign-in">Sign in to class</a></div> : <>
      {!data && !error && <p role="status">Loading…</p>}
      {error && <div className="msg msg-error" role="alert">{error}<button className="btn" onClick={/*
     * Handle the click event for this control.
     */
    () => setAttempt(/*
     * Compute the next attempt state from its previous value.
     */
    value => value + 1)}>Try again</button></div>}
      {data && <><p className="sub">{formatSessionDate(data.session_date)}</p>
        {data.message && <p role="status">{data.message}</p>}
        <ul className={styles.list}>{data.materials.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    file => <li key={file.id} className={styles.file}>
          <span>{file.file_name}</span><a className="btn" href={materialDownload(file.id)}>Download<span className={styles.srOnly}> {file.file_name}</span></a>
        </li>)}</ul><p className="hint">You can return on this phone for 24 hours after signing in.</p></>}
    </>}
  </>;
}
