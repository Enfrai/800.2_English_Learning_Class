import type { ReactNode } from "react";
import PublicNavigation from "./public-navigation";
import styles from "./club-home.module.css";
export default function PublicFrame({ children }: { children: ReactNode }) {
  return <div className={styles.frame}><PublicNavigation />{children}</div>;
}
