import type { TimelineItem } from "./timelineTypes";

export function timelineItemTitle(item: TimelineItem): string {
  switch (item.type) {
    case "planner_message":
      return "Planner";
    case "reasoning_summary":
      return "Reasoning summary";
    case "plan_update":
      return item.title;
    case "executor_step":
      return item.title;
    case "tool_call":
      return item.tool_name;
    case "command_execution":
      return item.command.join(" ");
    case "file_change":
      return item.path;
    case "approval":
      return item.action_type;
    case "verification":
      return "Verification";
    case "final_summary":
      return "Final summary";
    default:
      return "Timeline item";
  }
}

export function timelineItemStatus(item: TimelineItem): string {
  if ("status" in item && typeof item.status === "string") return item.status;
  return item.type.replaceAll("_", " ");
}
