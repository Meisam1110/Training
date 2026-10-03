import { createApi, createClient } from "./client";
import { createMockFetch } from "./mock/server";

export const USE_MOCK = import.meta.env.VITE_MOCK === "1";

/** Real client by default; in-memory mock when built/served with VITE_MOCK=1. */
export function makeApi(onUnauthorized: () => void) {
  if (USE_MOCK) {
    const mock = createMockFetch();
    return createApi(createClient({ fetchImpl: mock.fetch, onUnauthorized, simulateUpload: true }));
  }
  return createApi(createClient({ onUnauthorized }), { wire: true });
}
