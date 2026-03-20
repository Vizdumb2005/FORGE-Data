import { useEffect, useRef, useCallback, useState } from "react";
import { getAccessToken } from "@/lib/auth";

type MessageHandler = (data: unknown) => void;

interface UseWebSocketOptions {
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (err: Event) => void;
  reconnect?: boolean;
  maxRetries?: number;
}

/**
 * WebSocket hook with JSON message dispatch and exponential-backoff reconnection.
 */
export function useWebSocket(url: string | null, options: UseWebSocketOptions = {}) {
  const { reconnect = true, maxRetries = 10 } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<Map<string, MessageHandler>>(new Map());
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef = useRef(false);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (!url || unmountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    wsRef.current?.close();

    const token = getAccessToken();
    const fullUrl = token ? `${url}?token=${token}` : url;
    const ws = new WebSocket(fullUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      retriesRef.current = 0;
      setConnected(true);
      optionsRef.current.onOpen?.();
    };

    ws.onclose = () => {
      setConnected(false);
      optionsRef.current.onClose?.();

      if (reconnect && !unmountedRef.current && retriesRef.current < maxRetries) {
        const delay = Math.min(1000 * 2 ** retriesRef.current, 30000);
        retriesRef.current += 1;
        timerRef.current = setTimeout(() => {
          if (!unmountedRef.current) connect();
        }, delay);
      }
    };

    ws.onerror = (e) => optionsRef.current.onError?.(e);

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(event.data) as { type?: string; [k: string]: unknown };
        const type = msg.type ?? "__default__";
        handlersRef.current.get(type)?.(msg);
        handlersRef.current.get("*")?.(msg);
      } catch {
        // ignore non-JSON frames
      }
    };
  }, [url, reconnect, maxRetries]);

  useEffect(() => {
    unmountedRef.current = false;
    connect();
    return () => {
      unmountedRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  const on = useCallback((type: string, handler: MessageHandler) => {
    handlersRef.current.set(type, handler);
    return () => { handlersRef.current.delete(type); };
  }, []);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify(data));
  }, []);

  return { connect, send, on, ws: wsRef, connected };
}
