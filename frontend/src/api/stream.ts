import { RunChunk } from "./runs";
import { apiUrl, getAccessToken } from "./http";

export interface RunStreamHandlers {
  onChunk: (chunk: RunChunk) => void;
  onDone: (data: { run_id: string; status: string }) => void;
  onError?: (error: Error) => void;
}

export interface RunStreamSubscription {
  close: () => void;
}

export function subscribeRunStream(
  runId: string,
  handlers: RunStreamHandlers,
  after?: number,
): RunStreamSubscription {
  const controller = new AbortController();
  void readRunStream(runId, handlers, controller, after);
  return {
    close: () => controller.abort(),
  };
}

async function readRunStream(
  runId: string,
  handlers: RunStreamHandlers,
  controller: AbortController,
  after?: number,
): Promise<void> {
  const token = getAccessToken();
  const query = after === undefined ? "" : `?after=${after}`;
  try {
    const response = await fetch(apiUrl(`/api/runs/${runId}/stream${query}`), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: controller.signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(`Stream failed: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";
      for (const eventText of events) {
        dispatchSseEvent(eventText, handlers);
      }
    }
  } catch (error) {
    if (!controller.signal.aborted) {
      handlers.onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  }
}

function dispatchSseEvent(text: string, handlers: RunStreamHandlers): void {
  const lines = text.split("\n");
  const event = lines.find((line) => line.startsWith("event: "))?.slice(7).trim();
  const rawData = lines.find((line) => line.startsWith("data: "))?.slice(6);
  if (!event || !rawData) {
    return;
  }

  const data = JSON.parse(rawData);
  if (event === "chunk") {
    handlers.onChunk(data as RunChunk);
  }
  if (event === "done") {
    handlers.onDone(data as { run_id: string; status: string });
  }
  if (event === "error") {
    throw new Error(data.error ?? "Stream error");
  }
}
