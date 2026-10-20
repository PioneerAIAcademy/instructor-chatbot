/**
 * The "working on it" line (direction D): three Blue 4 dots at falling
 * opacity, then the status text. Announced politely to screen readers.
 */
export function ChatStatus({ text }: { text: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2.5 text-[15px] leading-snug text-ia-text"
    >
      <span aria-hidden="true" className="flex items-center gap-[5px] motion-safe:animate-pulse">
        <span className="h-2.5 w-2.5 rounded-full bg-ia-blue-4" />
        <span className="h-2.5 w-2.5 rounded-full bg-ia-blue-4 opacity-60" />
        <span className="h-2.5 w-2.5 rounded-full bg-ia-blue-4 opacity-30" />
      </span>
      <span>{text}</span>
    </div>
  );
}
