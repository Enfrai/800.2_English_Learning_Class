/*
 * Render approved club information and entry points for public visitors.
 * Author: SandhyaCodes1
 * Date: 26 Oct 2026
 */

import config from "@/content/club.json";
import { clubInformation, PUBLIC_COPY as copy } from "@/lib/club-information";
import styles from "./club-home.module.css";

/*
 * Render the club home interface and its associated content.
 */
export default function ClubHome() {
  const info = clubInformation(config);
  return <div className={styles.home}>
    <a className={styles.skip} href="#class-information">{copy.skip}</a>
    <main className={`page ${styles.main}`}>
      <h1>{copy.title}</h1>
      <p>{copy.intro}</p>
      <section id="class-information" className={styles.information} aria-labelledby="class-heading" tabIndex={-1}>
        <h2 id="class-heading">{copy.details}</h2>
        {info.sample && <p className={`msg msg-info ${styles.notice}`}>{copy.sample}</p>}
        <dl className={styles.facts}>
          <div className="card"><dt>{copy.day}</dt><dd>{info.day}</dd></div>
          <div className="card"><dt>{copy.time}</dt><dd>{info.time}</dd></div>
          <div className="card"><dt>{copy.venue}</dt><dd>{info.venue}<br />{info.address}</dd></div>
          <div className="card"><dt>{copy.contact}</dt><dd>{info.contact.label}<br /><a href={info.contact.href}>{info.contact.value}</a></dd></div>
        </dl>
      </section>
      <section aria-labelledby="join-heading"><h2 id="join-heading">{copy.join}</h2>
        {info.greeting && <p lang="mi">{info.greeting}</p>}
        <p>{copy.walkIn}</p><p>{copy.noAccount}</p>
      </section>
    </main>
  </div>;
}
