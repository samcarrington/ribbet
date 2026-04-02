import type { Decision } from "../types";

interface Props {
  decisions: Decision[];
}

export function Decisions({ decisions }: Props) {
  if (decisions.length === 0) {
    return <p className="text-gray-500 text-xs">No decisions detected yet</p>;
  }
  return (
    <ul className="space-y-1">
      {decisions.map((d) => (
        <li key={d.id} className="text-sm text-gray-200 flex items-start gap-2">
          <span className="text-green-400 mt-0.5">!</span>
          <span>{d.text}</span>
        </li>
      ))}
    </ul>
  );
}
