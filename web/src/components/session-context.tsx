/*
 * Provide typed React context for the authenticated staff session.
 * Author: Leonwu2026
 * Date: 25 Oct 2026
 */

"use client";

import { createContext, useContext } from "react";
import type { Session } from "@/lib/session";

/** UI-only view of the server-validated session; backend permissions remain authoritative. */
export const SessionContext = createContext<Session | null>(null);
/*
 * Read the staff identity from SessionContext and reject use outside its provider.
 */
export const useSession = () => useContext(SessionContext);
