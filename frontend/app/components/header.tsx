"use client";

import { Plus } from "lucide-react";
import Image from "next/image";
import { useChromeStrings } from "../lib/use-chrome-strings";
import { SettingsMenu } from "./settings-menu";

// The top bar on BYU gold #FFC328, in light and dark mode: the BYU-Pathway
// logo (its dark-gray artwork is about 6:1 on gold) and "Instructor
// Assistant" on the left; New chat (in a chat) and the settings gear on the
// right. Everything on the bar is near-black, and so is its focus ring.
export default function Header({ onNewChat }: { onNewChat?: () => void }) {
  const strings = useChromeStrings();
  return (
    <header className="relative z-50 flex h-14 w-full flex-shrink-0 items-center justify-between gap-2 bg-ia-gold px-3 text-ia-on-gold sm:px-5">
      <a
        href="/"
        aria-label={strings.homeAria}
        className="flex min-w-0 items-center gap-2 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-ia-on-gold focus-visible:ring-offset-4 focus-visible:ring-offset-ia-gold min-[400px]:gap-2.5 sm:gap-3"
      >
        <Image
          src="/pathway-horizontal-logo.png"
          alt="BYU-Pathway Worldwide"
          width={178}
          height={23}
          priority
          className="h-[11px] w-auto shrink-0 min-[400px]:h-[15px] sm:h-[20px]"
        />
        <span aria-hidden="true" className="h-5 w-px shrink-0 bg-[#1F1E1D]/30 sm:h-6" />
        <span className="truncate text-[14px] font-bold min-[400px]:text-[15px] sm:text-[17px]">
          {strings.headerTitle}
        </span>
      </a>

      <div className="flex shrink-0 items-center gap-1 sm:gap-2">
        {onNewChat && (
          <button
            type="button"
            onClick={onNewChat}
            aria-label={strings.newChat}
            className="inline-flex h-10 items-center gap-1.5 rounded-full border border-[#1F1E1D]/25 px-2.5 text-sm font-semibold transition-colors hover:bg-[#1F1E1D]/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia-on-gold focus-visible:ring-offset-2 focus-visible:ring-offset-ia-gold sm:h-9 sm:px-3"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            <span className="hidden sm:inline">{strings.newChat}</span>
          </button>
        )}
        <SettingsMenu />
      </div>
    </header>
  );
}
