"use client";

import { createContext, useContext } from "react";
import type { Session } from "@/lib/session";

/** UI-only view of the server-validated session; backend permissions remain authoritative. */
export const SessionContext = createContext<Session | null>(null);
export const useSession = () => useContext(SessionContext);
