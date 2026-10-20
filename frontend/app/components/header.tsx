import Image from "next/image";
import { SettingsMenu } from "./settings-menu";

/**
 * Direction D, "light chrome": a white header with the BYU-Pathway logo as-is
 * (Gray 4 on white, an approved lockup), a divider, and the product name.
 * Blue is kept for things you can act on. Dark mode puts the header on
 * Gray 4; the logo image is lightened there with a filter (the file itself is
 * the same), since Gray 4 artwork on a Gray 4 bar would disappear.
 */
export default function Header() {
  return (
    <header className="relative z-50 flex h-14 w-full flex-shrink-0 items-center justify-between gap-4 border-b border-ia-header-border bg-ia-header-bg px-4 text-ia-header-text sm:h-16 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <a
          href="/"
          aria-label="BYU-Pathway Instructor Assistant home"
          className="inline-flex flex-shrink-0 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-ia-focus focus-visible:ring-offset-4 focus-visible:ring-offset-ia-header-bg"
        >
          {/* Phones show the icon logo (the prototype drops the wordmark
              there) so the title fits; wider screens the full logo. */}
          <Image
            src="/BYU-pathway-icon-logo.png"
            alt="BYU-Pathway Worldwide"
            width={28}
            height={27}
            priority
            className="h-7 w-auto sm:hidden"
          />
          <Image
            src="/pathway-horizontal-logo.png"
            alt="BYU-Pathway Worldwide"
            width={140}
            height={18}
            priority
            className="hidden h-[20px] w-auto sm:block dark:[filter:brightness(0)_invert(0.89)]"
          />
        </a>
        <span aria-hidden="true" className="h-6 w-px flex-shrink-0 bg-ia-header-border" />
        <h1 className="truncate text-[17px] font-bold leading-tight sm:text-lg">
          Instructor Assistant
        </h1>
      </div>
      <div className="flex flex-shrink-0 items-center gap-1">
        <SettingsMenu />
      </div>
    </header>
  );
}
