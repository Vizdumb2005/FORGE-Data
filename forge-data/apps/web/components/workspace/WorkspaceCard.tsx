"use client";

import Link from "next/link";
import { Users, Clock } from "lucide-react";
import { formatDate, initials } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import type { Workspace } from "@/types";

interface WorkspaceCardProps {
  workspace: Workspace;
}

const ROLE_COLORS: Record<string, string> = {
  admin: "bg-forge-accent/20 text-forge-accent border-forge-accent/30",
  editor: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  analyst: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  viewer: "bg-forge-border text-forge-muted border-forge-border",
};

export default function WorkspaceCard({ workspace }: WorkspaceCardProps) {
  return (
    <Link
      href={`/workspace/${workspace.id}`}
      className="group block rounded-lg border border-forge-border bg-forge-surface p-4 transition-all duration-200 hover:border-forge-accent/30 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-forge-accent/5"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-foreground group-hover:text-forge-accent transition-colors truncate">
            {workspace.name}
          </h3>
          <p className="mt-0.5 text-xs text-forge-muted truncate">
            {workspace.description || "No description"}
          </p>
        </div>
        {workspace.role && (
          <Badge
            variant="outline"
            className={`ml-2 shrink-0 text-[10px] ${ROLE_COLORS[workspace.role] ?? ROLE_COLORS.viewer}`}
          >
            {workspace.role}
          </Badge>
        )}
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-xs text-forge-muted">
          <span className="flex items-center gap-1">
            <Users className="h-3 w-3" />
            {workspace.member_count}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatDate(workspace.updated_at)}
          </span>
        </div>

        {/* Member avatars (up to 3) */}
        <div className="flex -space-x-1.5">
          {Array.from({ length: Math.min(workspace.member_count, 3) }).map(
            (_, i) => (
              <Avatar key={i} className="h-5 w-5 border border-forge-surface">
                <AvatarFallback className="text-[8px] bg-forge-border text-forge-muted">
                  {String.fromCharCode(65 + i)}
                </AvatarFallback>
              </Avatar>
            )
          )}
          {workspace.member_count > 3 && (
            <div className="flex h-5 w-5 items-center justify-center rounded-full border border-forge-surface bg-forge-border text-[8px] text-forge-muted">
              +{workspace.member_count - 3}
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}
