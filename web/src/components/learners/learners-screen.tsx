/* Show the class list, learner forms and individual attendance history.
 * Author: Pei Wu
 * Date: 23 Oct 2026
 * Updated: Shuohui Liu, 26 Oct 2026
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import CsvUpload from "./csv-upload";
import { useSession } from "@/components/session-context";
import LearnerForm from "./learner-form";
import { type Learner, LoginRequiredError, listLearners } from "@/lib/learners-api";

type FormTarget = { learner: Learner | null } | null;
type LoadState = "loading" | "ready" | "login-required" | "failed";

const LEARNER_SAVED = "Learner saved";

/*
 * Render the learners screen interface and its associated content.
 */
export default function LearnersScreen() {
  const session = useSession();
  const [showImport, setShowImport] = useState(false);
  const [learners, setLearners] = useState<Learner[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [formTarget, setFormTarget] = useState<FormTarget>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(/*
     * Run the memoized load operation for the current dependencies.
     */
    async () => {
    try {
      setLearners(await listLearners());
      setLoadState("ready");
    } catch (error) {
      setLoadState(error instanceof LoginRequiredError ? "login-required" : "failed");
    }
  }, []);

  useEffect(/*
     * Synchronize the component with its current dependencies and manage effect
     * resources.
     */
    () => {
    void load();
  }, [load]);

  /*
   * Open the learner editor for a new or existing learner.
   */
  function openForm(learner: Learner | null) {
    setNotice(null);
    setFormTarget({ learner });
  }

  /*
   * Apply the saved learner and close the editor after a successful save.
   */
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
        <button type="button" className="btn" onClick={/*
     * Handle the click event for this control.
     */
    () => openForm(null)}>
          Add learner
        </button>
        {/* Visibility uses SessionShell's validated role; the import API also enforces it. */}
        {session?.role === "coordinator" && <button type="button" className="btn btn-secondary"
          aria-expanded={showImport} onClick={/*
     * Handle the click event for this control.
     */
    () => setShowImport(/*
     * Compute the next show import state from its previous value.
     */
    current => !current)}>
          {showImport ? "Close CSV import" : "Import CSV"}
        </button>}
      </div>
      {session?.role === "coordinator" && showImport && <div className="no-print">
        <CsvUpload onImported={/*
     * Handle the imported event for this control.
     */
    () => void load()} />
      </div>}
      {notice && (
        <div className="msg msg-success" role="status">
          {notice}
        </div>
      )}

      {loadState === "loading" && <p role="status">Loading learners…</p>}
      {loadState === "failed" && (
        <div className="msg msg-error" role="alert">
          The learners could not be loaded. Please try again.{" "}
          <button type="button" className="btn btn-secondary" onClick={/*
     * Handle the click event for this control.
     */
    () => void load()}>
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
          onSaved={/*
     * Handle the saved event for this control.
     */
    () => void handleSaved()}
          onCancel={/*
     * Handle the cancel event for this control.
     */
    () => setFormTarget(null)}
          onLoginRequired={/*
     * Handle the login required event for this control.
     */
    () => setLoadState("login-required")}
        />
      )}
    </>
  );
}

/*
 * Render the learner table interface and its associated content.
 */
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
        {learners.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    (learner) => {
          const name = `${learner.first_name} ${learner.family_name}`;
          return (
            <tr key={learner.id}>
              {/* A 100-character name with no spaces must wrap, not widen the table. */}
              <td style={{ overflowWrap: "anywhere" }}>{name}</td>
              <td>{learner.first_language ?? "–"}</td>
              <td>{learner.contact ?? "–"}</td>
              <td className="no-print">
                <div className="row">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    aria-label={`Edit ${name}`}
                    onClick={/*
     * Handle the click event for this control.
     */
    () => onEdit(learner)}
                  >
                    Edit
                  </button>
                  {/* Attendance history is US-016 (UI design document 6.17). */}
                  <Link className="btn btn-secondary" href={`/learners/${encodeURIComponent(learner.id)}/history`} aria-label={`Attendance history for ${name}`}>
                    History
                  </Link>
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
