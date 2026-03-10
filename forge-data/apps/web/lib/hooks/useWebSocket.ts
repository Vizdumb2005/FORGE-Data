import { useEffect, useRef, useCallback } from "react";
import { getAccessToken } from "@/lib/auth";

type MessageHandler = (data: unknown) => void;

interface UseWebSocketOptions {
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (err: Event) => void;
}

/**
 * Minimal hook wrapping a native WebSocket.
 * The socket is opened lazily on first `send()` or when `connect()` is called.
 */
export function useWebSocket(url: string | null, options: UseWebSocketOptions = {}) {
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<Map<string, MessageHandler>>(new Map());
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const connect = useCallback(() => {
    if (!url || wsRef.current?.readyState === WebSocket.OPEN) return;

    const token = getAccessToken();
    const fullUrl = token ? `${url}?token=${token}` : url;
    const ws = new WebSocket(fullUrl);
    wsRef.current = ws;

    ws.onopen = () => optionsRef.current.onOpen?.();
    ws.onclose = () => optionsRef.current.onClose?.();
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
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  const on = useCallback((type: string, handler: MessageHandler) => {
    handlersRef.current.set(type, handler);
    return () => handlersRef.current.delete(type);
  }, []);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify(data));
  }, []);

  return { connect, send, on, ws: wsRef };
}
