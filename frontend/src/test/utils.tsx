import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiProvider, AuthProvider } from "../app-context";
import { createApi, createClient, type FetchLike } from "../api/client";
import { createMockFetch } from "../api/mock/server";
import { ToastProvider } from "../components/Toast";
import type { User } from "../api/types";

export async function setup(role: "admin" | "hr" | "viewer" = "hr") {
  const mock = createMockFetch({ latency: 0, storage: false });
  const calls: { method: string; url: string; body?: unknown }[] = [];
  const spy: FetchLike = (url, init) => { calls.push({ method: init?.method ?? "GET", url, body: init?.body }); return mock.fetch(url, init); };
  const api = createApi(createClient({ fetchImpl: spy }));
  const res = await api.login(role, "demo");
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (el: ReactElement, user: User | null = res.user) => render(
    <QueryClientProvider client={qc}><ApiProvider api={api}><ToastProvider><AuthProvider initialUser={user}>{el}</AuthProvider></ToastProvider></ApiProvider></QueryClientProvider>);
  return { api, calls, ui, mock, user: res.user };
}
