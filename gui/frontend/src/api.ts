// api.ts — SSE client and REST helpers

import type { StageEvent, PipelineResult, HealthResponse } from './types';

const API_BASE = '/api';

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json() as Promise<HealthResponse>;
}

export interface StreamCallbacks {
  onStage:        (event: StageEvent) => void;
  onResult:       (result: PipelineResult) => void;
  /** Fired when the server emits an `error` SSE event mid-stream. */
  onError:        (message: string) => void;
  /** Fired for connection / HTTP-level failures before streaming begins. */
  onNetworkError: (message: string) => void;
}

/**
 * POST a query and stream SSE stage + result events back.
 * Returns a cleanup function to abort early.
 */
export function streamQuery(
  query: string,
  callbacks: StreamCallbacks,
  geneId?: string,
): () => void {
  const controller = new AbortController();

  (async () => {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/query`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body:    JSON.stringify({ query, gene_id: geneId ?? null, verbose: false }),
        signal:  controller.signal,
      });
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        callbacks.onNetworkError(`Network error: ${(err as Error).message}`);
      }
      return;
    }

    if (!response.ok || !response.body) {
      callbacks.onNetworkError(`Server error: HTTP ${response.status}`);
      return;
    }

    const reader  = response.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';

    while (true) {
      let done = false;
      let chunk: Uint8Array | undefined;
      try {
        const read = await reader.read();
        done  = read.done;
        chunk = read.value;
      } catch { break; }

      if (done) break;
      buffer += decoder.decode(chunk, { stream: true });
      const parts = buffer.split(/\r?\n\r?\n/);
      buffer = parts.pop() ?? '';

      for (const part of parts) {
        const lines = part.split(/\r?\n/);
        let eventType = 'message';
        let data      = '';
        for (const line of lines) {
          if (line.startsWith('event:'))      eventType = line.slice(6).trim();
          else if (line.startsWith('data:')) data      = line.slice(5).trim();
        }
        if (!data) continue;
        try {
          const parsed = JSON.parse(data) as Record<string, unknown>;
          if      (eventType === 'stage')  callbacks.onStage(parsed as unknown as StageEvent);
          else if (eventType === 'result') callbacks.onResult(parsed as unknown as PipelineResult);
          else if (eventType === 'error')  callbacks.onError((parsed as { message: string }).message);
        } catch { /* skip malformed frames */ }
      }
    }
  })();

  return () => controller.abort();
}
