"use client";
import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import { listLessons, type Lesson } from "@/lib/lessons-api";
export default function SessionLesson({ sessionId }: { sessionId: string }) {
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    Promise.all([listLessons(), apiRequest(`/api/access/sessions/${sessionId}/lesson`)])
      .then(([items, response]) => { if (response.status !== 200) throw new Error(); const link = response.body as { lesson_id: string | null }; if (active) { setLessons(items); setSelected(link.lesson_id || ""); setReady(true); } })
      .catch(() => { if (active) setMessage("The linked lesson could not be loaded."); });
    return () => { active = false; };
  }, [sessionId]);
  async function save() {
    setSaving(true); setMessage("");
    try {
      const response = await apiRequest(`/api/access/sessions/${sessionId}/lesson`, { method: "PUT", body: JSON.stringify({ lesson_id: selected || null }) });
      if (response.status !== 200) throw new Error();
      setMessage("Lesson saved for this class.");
    } catch { setMessage("The lesson could not be saved. Please try again."); }
    finally { setSaving(false); }
  }
  return <section aria-label="Class lesson"><h2>Class lesson</h2>
    <p>Shared materials from this lesson are available after learners sign in.</p>
    {ready && <><label htmlFor="class-lesson">Lesson</label><select id="class-lesson" value={selected} onChange={event => setSelected(event.target.value)}>
      <option value="">No lesson</option>{selected && !lessons.some(item => item.id === selected) && <option value={selected}>Unavailable lesson</option>}
      {lessons.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
    </select><button type="button" className="btn" disabled={saving} onClick={() => void save()}>{saving ? "Saving…" : "Save lesson"}</button></>}
    {message && <p role="status">{message}</p>}
  </section>;
}
