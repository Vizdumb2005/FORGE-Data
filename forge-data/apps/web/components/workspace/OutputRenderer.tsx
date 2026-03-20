"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CellOutput } from "@/types";

interface OutputRendererProps {
  outputs: CellOutput[];
  maxHeight?: string;
}

export default function OutputRenderer({ outputs, maxHeight = "400px" }: OutputRendererProps) {
  if (outputs.length === 0) return null;

  return (
    <div className="border-t border-forge-border overflow-auto" style={{ maxHeight }}>
      {outputs.map((output, i) => (
        <OutputItem key={i} output={output} />
      ))}
    </div>
  );
}

function OutputItem({ output }: { output: CellOutput }) {
  const { mime_type, data } = output;

  // Stream stdout
  if (mime_type === "stream/stdout") {
    const text = (data as Record<string, unknown>).text as string;
    return (
      <pre className="whitespace-pre-wrap px-3 py-1 font-mono text-xs text-forge-text bg-forge-bg/50">
        {text}
      </pre>
    );
  }

  // Stream stderr
  if (mime_type === "stream/stderr") {
    const text = (data as Record<string, unknown>).text as string;
    return (
      <pre className="whitespace-pre-wrap px-3 py-1 font-mono text-xs text-amber-400 bg-forge-bg/50">
        {text}
      </pre>
    );
  }

  // Error with traceback
  if (mime_type === "error") {
    return <ErrorOutput data={data as Record<string, unknown>} />;
  }

  // Image
  if (mime_type === "image/png" || mime_type.startsWith("image/")) {
    const imgData = (data as Record<string, string>)["image/png"] ?? (data as Record<string, string>).image;
    if (imgData) {
      const src = imgData.startsWith("data:") ? imgData : `data:image/png;base64,${imgData}`;
      return (
        <div className="p-3 bg-forge-bg/50">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={src} alt="output" className="max-w-full rounded" />
        </div>
      );
    }
  }

  // HTML output — sandboxed iframe
  if (mime_type === "text/html" || (data as Record<string, unknown>)["text/html"]) {
    const html = ((data as Record<string, unknown>)["text/html"] ?? (data as Record<string, unknown>).text ?? "") as string;
    return (
      <div className="p-3 bg-forge-bg/50">
        <iframe
          srcDoc={html}
          sandbox="allow-scripts"
          className="w-full border-0 rounded bg-white"
          style={{ minHeight: 100, maxHeight: 400 }}
          title="HTML output"
        />
      </div>
    );
  }

  // text/plain or fallback
  const text =
    ((data as Record<string, unknown>)["text/plain"] as string) ??
    ((data as Record<string, unknown>).text as string) ??
    JSON.stringify(data, null, 2);

  return (
    <pre className="whitespace-pre-wrap px-3 py-2 font-mono text-xs text-forge-text bg-forge-bg/50">
      {text}
    </pre>
  );
}

function ErrorOutput({ data }: { data: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false);
  const ename = (data.ename as string) ?? "Error";
  const evalue = (data.evalue as string) ?? "";
  const traceback = (data.traceback as string[]) ?? [];

  return (
    <div className="bg-red-950/30 border-l-2 border-red-500 px-3 py-2">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-3.5 w-3.5 text-red-400 shrink-0" />
        <span className="font-mono text-xs">
          <span className="font-bold text-red-400">{ename}</span>
          {evalue && <span className="text-red-300">: {evalue}</span>}
        </span>
      </div>
      {traceback.length > 0 && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-1 flex items-center gap-1 text-[10px] text-red-400/70 hover:text-red-400"
          >
            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            Traceback ({traceback.length} frames)
          </button>
          {expanded && (
            <pre className={cn(
              "mt-1 whitespace-pre-wrap font-mono text-[11px] text-red-300/80",
              "max-h-60 overflow-auto"
            )}>
              {traceback.join("\n")}
            </pre>
          )}
        </>
      )}
    </div>
  );
}
