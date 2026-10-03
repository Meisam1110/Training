import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/layout.css";
import { makeApi } from "./api";
import { ApiProvider, AuthProvider, authFlag, toLogin } from "./app-context";
import { ToastProvider } from "./components/Toast";
import { App } from "./App";

document.documentElement.lang = "fa";
document.documentElement.dir = "rtl";

const bus = { onUnauthorized: () => {} };
const api = makeApi(() => bus.onUnauthorized());
const qc = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 15_000 } } });
bus.onUnauthorized = () => { const was = authFlag.authed; if (was) authFlag.expired = true; qc.clear(); window.dispatchEvent(new Event("tms:unauthorized")); /* sign-out state first, so the router never bounces a public route to "/" */ toLogin(was); };

// Start the (single, variable) font early and hold the first paint briefly for it, so text never re-flows after load.
const fontReady = Promise.race([document.fonts?.load('400 1em Vazirmatn').then(() => document.fonts.load('700 1em Vazirmatn')) ?? Promise.resolve(), new Promise((r) => setTimeout(r, 2500))]);
void fontReady.then(() => createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <ApiProvider api={api}>
        <ToastProvider>
          <AuthProvider>
            <UnauthBridge />
            <App />
          </AuthProvider>
        </ToastProvider>
      </ApiProvider>
    </QueryClientProvider>
  </React.StrictMode>,
));

import { useEffect } from "react";
import { useAuth } from "./app-context";
function UnauthBridge() {
  const { setUser } = useAuth();
  useEffect(() => { const f = () => setUser(null); window.addEventListener("tms:unauthorized", f); return () => window.removeEventListener("tms:unauthorized", f); }, [setUser]);
  return null;
}
