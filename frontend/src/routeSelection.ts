import type { RouteType } from "./types";

type Selection = {
  recommendation_id: string;
  user_id: string;
  selected_route_type: RouteType;
};

class SelectionHttpError extends Error {
  status: number;
  constructor(status: number) {
    super(`Route selection HTTP ${status}`);
    this.status = status;
  }
}

// Serialize choices so a delayed retry cannot overwrite a newer selection.
export function createRouteSelectionSaver(
  send: typeof fetch = fetch,
  wait: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
) {
  let queue = Promise.resolve();
  return (selection: Selection): Promise<void> => {
    const save = async () => {
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const response = await send("/api/agent/route-selections", {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify(selection),
            keepalive: true,
            signal: AbortSignal.timeout(10_000),
          });
          if (!response.ok) throw new SelectionHttpError(response.status);
          await response.json();
          return;
        } catch (error) {
          const retryable = error instanceof SelectionHttpError
            ? [500, 502, 503, 504].includes(error.status)
            : error instanceof TypeError || (error instanceof DOMException && ["TimeoutError", "AbortError"].includes(error.name));
          if (!retryable || attempt === 2) throw error;
          await wait(1000 * (attempt + 1));
        }
      }
    };
    const result = queue.then(save);
    queue = result.catch(() => undefined);
    return result;
  };
}
