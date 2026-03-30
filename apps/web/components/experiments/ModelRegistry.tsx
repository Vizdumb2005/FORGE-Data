"use client";

import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { RegistryModel } from "@/types";

interface ModelRegistryProps {
  models: RegistryModel[];
}

export default function ModelRegistry({ models }: ModelRegistryProps) {
  const [testInput, setTestInput] = useState("{}");
  const [testOutput, setTestOutput] = useState<string>("");

  return (
    <div className="rounded-lg border border-forge-border bg-forge-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <FlaskConical className="h-4 w-4 text-forge-accent" />
        <h3 className="text-sm font-semibold">Model Registry</h3>
      </div>
      {models.length === 0 ? (
        <p className="text-sm text-forge-muted">No deployed models yet.</p>
      ) : (
        <div className="space-y-3">
          {models.map((model) => {
            const latest = model.latest_versions[0];
            return (
              <div key={model.name} className="rounded border border-forge-border/70 p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">{model.name}</p>
                    <p className="font-mono text-xs text-forge-muted">
                      Inference endpoint: `/api/v1/inference/{model.name}`
                    </p>
                  </div>
                  {latest ? (
                    <Badge variant={latest.stage === "Production" ? "success" : "warning"}>
                      {latest.stage} v{latest.version}
                    </Badge>
                  ) : null}
                </div>
                <div className="mt-3 rounded border border-forge-border/50 p-2">
                  <p className="mb-2 text-xs text-forge-muted">Test model</p>
                  <div className="flex items-center gap-2">
                    <Input
                      value={testInput}
                      onChange={(e) => setTestInput(e.target.value)}
                      placeholder='{"feature": 1}'
                    />
                    <Button
                      variant="secondary"
                      onClick={() => setTestOutput(`POST payload: ${testInput}`)}
                    >
                      Test model
                    </Button>
                  </div>
                  {testOutput ? (
                    <pre className="mt-2 overflow-auto rounded bg-forge-bg p-2 text-xs">{testOutput}</pre>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

