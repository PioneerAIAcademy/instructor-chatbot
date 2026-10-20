import { User2 } from "lucide-react";

/** Assistant avatar (direction D): a Blue 4 circle with a white sparkle. */
export default function ChatAvatar({ role }: { role: string }) {
  if (role === "user") {
    return (
      <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-full border border-ia-border bg-ia-surface text-ia-text">
        <User2 aria-hidden="true" className="h-4 w-4" />
      </div>
    );
  }

  return (
    <div
      aria-hidden="true"
      className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-full bg-ia-blue-4 text-white"
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 2.5 14.6 9.4 21.5 12 14.6 14.6 12 21.5 9.4 14.6 2.5 12 9.4 9.4z" />
      </svg>
    </div>
  );
}
