// Recipients for a run come straight from its enrollments (the backend now returns `email` on each enrollment).
import { useQuery } from "@tanstack/react-query";
import { useApi } from "../app-context";
import type { Recipient } from "../api/types";

export function useRunRecipients(runId: number | null | undefined, enabled = true) {
  const api = useApi();
  return useQuery({
    queryKey: ["recipients", runId], enabled: enabled && !!runId,
    queryFn: async (): Promise<Recipient[]> => {
      const out: Recipient[] = []; const seen = new Set<string>();
      for (let page = 1; page <= 10; page++) { // backend caps page_size at 200
        const r = await api.runEnrollments(runId!, { page, page_size: 200 });
        for (const e of r.items) if (e.motivation !== "no" && e.email && !seen.has(e.email.toLowerCase())) { seen.add(e.email.toLowerCase()); out.push({ email: e.email, name: e.name_fa }); }
        if (page * 200 >= r.total) break;
      }
      return out;
    },
  });
}
