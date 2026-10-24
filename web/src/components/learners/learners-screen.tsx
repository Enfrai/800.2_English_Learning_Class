/* Learners page: the class list and the add or edit form (UI design document 6.4).
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import LearnerForm from "./learner-form";
import { type Learner, LoginRequiredError, listLearners } from "@/lib/learners-api";

type FormTarget = { learner: Learner | null } | null;
type LoadState = "loading" | "ready" | "login-required" | "failed";

const LEARNER_SAVED = "Learner saved";

export default function LearnersScreen() {
  const [learners, setLearners] = useState<Learner[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [formTarget, setFormTarget] = useState<FormTarget>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLearners(await listLearners());
      setLoadState("ready");
    } catch (error) {
      setLoadState(error instanceof LoginRequiredError ? "login-required" : "failed");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function openForm(learner: Learner | null) {
    setNotice(null);
    setFormTarget({ learner });
  }

  async function handleSaved() {
    setFormTarget(null);
    setNotice(LEARNER_SAVED);
    await load();
  }

  if (loadState === "login-required") {
    return (
      <>
        <h1>Learners</h1>
        <div className="msg msg-error" role="alert">
          Please log in to see the learners. <a href="/">Log in</a>
        </div>
      </>
    );
  }

  return (
    <>
      <h1>Learners</h1>
      <p className="sub">The class list. Keep only what the club needs.</p>

      {/* The kit's .row has no margin, so keep the button off the table. */}
      <div className="row no-print" style={{ marginBottom: "var(--space-4)" }}>
        <button type="button" className="btn" onClick={() => openForm(null)}>
          Add learner
        </button>
      </div>
      {notice && (
        <div className="msg msg-success" role="status">
          {notice}
        </div>
      )}

      {loadState === "loading" && <p role="status">Loading learners…</p>}
      {loadState === "failed" && (
        <div className="msg msg-error" role="alert">
          The learners could not be loaded. Please try again.{" "}
          <button type="button" className="btn btn-secondary" onClick={() => void load()}>
            Try again
          </button>
        </div>
      )}
      {loadState === "ready" && learners.length === 0 && (
        <div className="msg msg-info">No learners yet. Use Add learner to start the class list.</div>
      )}
      {loadState === "ready" && learners.length > 0 && (
        <LearnerTable learners={learners} onEdit={openForm} />
      )}

      {formTarget && (
        <LearnerForm
          // A new key gives a fresh form when another learner is chosen.
          key={formTarget.learner?.id ?? "new"}
          learner={formTarget.learner}
          onSaved={() => void handleSaved()}
          onCancel={() => setFormTarget(null)}
          onLoginRequired={() => setLoadState("login-required")}
        />
      )}
    </>
  );
}

function LearnerTable({
  learners,
  onEdit,
}: {
  learners: Learner[];
  onEdit: (learner: Learner) => void;
}) {
  return (
    <table className="data">
      <thead>
        <tr>
          <th scope="col">Name</th>
          <th scope="col">First language</th>
          <th scope="col">Phone or email</th>
          <th scope="col" className="no-print">
            Actions
          </th>
        </tr>
      </thead>
      <tbody>
        {learners.map((learner) => {
          const name = `${learner.first_name} ${learner.family_name}`;
          return (
            <tr key={learner.id}>
              <td>{name}</td>
              <td>{learner.first_language ?? "–"}</td>
              <td>{learner.contact ?? "–"}</td>
              <td className="no-print">
                <div className="row">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    aria-label={`Edit ${name}`}
                    onClick={() => onEdit(learner)}
                  >
                    Edit
                  </button>
                  {/* Attendance history is US-016 (Later, UI design document 6.17). */}
                  <button type="button" className="btn btn-later" disabled>
                    History (later)
                  </button>
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
