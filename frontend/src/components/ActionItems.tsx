import type { ActionItem } from "../types";

interface Props {
  actions: ActionItem[];
}

export function ActionItems({ actions }: Props) {
  if (actions.length === 0) {
    return <p className="text-gray-500 text-xs">No action items detected yet</p>;
  }
  return (
    <ul className="space-y-1">
      {actions.map((a) => (
        <li key={a.id} className="text-sm text-gray-200 flex items-start gap-2">
          <span className="text-amber-400 mt-0.5">*</span>
          <span>{a.text}</span>
        </li>
      ))}
    </ul>
  );
}
