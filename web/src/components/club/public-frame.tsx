/*
 * Provide the public-page frame and shared navigation.
 * Author: Enfrai
 * Date: 26 Oct 2026
 */

import type { ReactNode } from "react";
import PublicNavigation from "./public-navigation";
import styles from "./club-home.module.css";
/*
 * Render the public frame interface and its associated content.
 */
export default function PublicFrame({ children }: { children: ReactNode }) {
  return <div className={styles.frame}><PublicNavigation />{children}</div>;
}
