"use client";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { CollaboratorPresence } from "@/lib/stores/workspaceStore";
import { initials } from "@/lib/utils";

interface PresenceBarProps {
  users: CollaboratorPresence[];
}

export default function PresenceBar({ users }: PresenceBarProps) {
  if (users.length === 0) return null;

  const visible = users.slice(0, 5);
  const remaining = users.length - visible.length;

  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex items-center gap-1.5">
        {visible.map((user) => {
          const editing = Boolean(user.cursor_cell_id);
          return (
            <Tooltip key={user.user_id}>
              <TooltipTrigger asChild>
                <div className="relative">
                  <Avatar className="h-7 w-7 border-2" style={{ borderColor: user.color }}>
                    <AvatarFallback className="text-[10px] font-semibold text-foreground">
                      {initials(user.user_name)}
                    </AvatarFallback>
                  </Avatar>
                  {editing ? (
                    <span
                      className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full animate-pulse"
                      style={{ backgroundColor: user.color }}
                    />
                  ) : null}
                </div>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <div className="text-xs">
                  <div className="font-medium">{user.user_name}</div>
                  <div className="text-forge-muted">
                    {user.cursor_cell_id ? `Editing Cell ${user.cursor_cell_id.slice(0, 6)}` : "Viewing"}
                  </div>
                </div>
              </TooltipContent>
            </Tooltip>
          );
        })}
        {remaining > 0 ? (
          <span className="rounded-full border border-forge-border px-2 py-0.5 text-[10px] text-forge-muted">
            +{remaining} more
          </span>
        ) : null}
      </div>
    </TooltipProvider>
  );
}
