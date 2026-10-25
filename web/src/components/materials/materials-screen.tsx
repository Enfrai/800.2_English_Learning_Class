"use client";
import { useEffect, useState } from "react";
import { getMaterials, materialDownload, SignInRequired, type Materials } from "@/lib/materials-api";
import { formatSessionDate } from "@/lib/dates";
import styles from "./materials.module.css";
export default function MaterialsScreen({ embedded = false }: { embedded?: boolean }) {
  const [data, setData] = useState<Materials | null>(null);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError(""); setData(null);
    const load = () => getMaterials().then(value => { if (active) setData(value); }).catch(reason => {
      if (!active) return;
      if (reason instanceof SignInRequired) { setData(null); setExpired(true); }
      else setError("Materials are not available right now. Please try again.");
    });
    void load();
    const timer = window.setInterval(() => void load(), 60000);
    return () => { active = false; window.clearInterval(timer); };
  }, [attempt]);
  return <>
    {embedded ? <h2>Lesson materials</h2> : <h1>Lesson materials</h1>}
    {expired ? <div role="status"><p>Please scan a class code and sign in again.</p><a className="btn" href="/sign-in">Sign in to class</a></div> : <>
      {!data && !error && <p role="status">Loading…</p>}
      {error && <div className="msg msg-error" role="alert">{error}<button className="btn" onClick={() => setAttempt(value => value + 1)}>Try again</button></div>}
      {data && <><p className="sub">{formatSessionDate(data.session_date)}</p>
        {data.message && <p role="status">{data.message}</p>}
        <ul className={styles.list}>{data.materials.map(file => <li key={file.id} className={styles.file}>
          <span>{file.file_name}</span><a className="btn" href={materialDownload(file.id)}>Download<span className={styles.srOnly}> {file.file_name}</span></a>
        </li>)}</ul><p className="hint">You can return on this phone for 24 hours after signing in.</p></>}
    </>}
  </>;
}
