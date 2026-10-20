import Image from "next/image";
import { SettingsMenu } from "./settings-menu";

// Upstream's header on brand blue #056CB6 (was gold). The gray logo artwork
// would be unreadable on it (about 2.4:1), so the logo, title, and gear show
// in white; the logo file itself is unchanged.

export default function Header() {
  return (
    <header className="relative z-50 w-full bg-[#056CB6] px-4 sm:px-6 pb-2 pt-0 min-[480px]:pt-2 min-[480px]:pb-2 flex-shrink-0">
      {/* Container for screens >= 480px - single row layout */}
      <div className="hidden min-[480px]:flex items-center justify-between w-full relative min-h-[40px]">
        {/* Logo */}
        <div className="flex items-center z-10">
          <a
            href="/"
            aria-label="BYU-Pathway Instructor Assistant home"
            className="cursor-pointer inline-flex rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-[6px] focus-visible:ring-offset-[#056CB6]"
          >
            <Image
              src="/pathway-horizontal-logo.png"
              alt="BYU Pathway Logo"
              width={140}
              height={18}
              className="h-[15px] sm:h-[24px] min-[570px]:h-[20px] w-auto [filter:brightness(0)_invert(1)]"
            />
          </a>
        </div>
        
        {/* Title - centered */}
        <div className="absolute left-1/2 transform -translate-x-1/2">
          <h1 className="font-semibold text-[18px] md:text-xl text-white whitespace-nowrap">
            Instructor Assistant
          </h1>
        </div>
        
        {/* Right side - Settings menu (all screens) */}
        <div className="flex items-center gap-1 sm:gap-2 z-10">
          <SettingsMenu />
        </div>
      </div>

      {/* Container for screens < 480px - wrapped layout */}
      <div className="min-[480px]:hidden relative -ml-2">
        {/* Logo - top left */}
        <a
          href="/"
          aria-label="BYU-Pathway Instructor Assistant home"
          className="cursor-pointer inline-flex rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-[6px] focus-visible:ring-offset-[#056CB6]"
        >
          <Image
            src="/pathway-horizontal-logo.png"
            alt="BYU Pathway Logo"
            width={140}
            height={18}
            className="h-[14px] w-auto [filter:brightness(0)_invert(1)]"
          />
        </a>
        
        {/* Settings Icon - absolute positioned, vertically centered */}
        <div className="absolute right-0 top-1/2 -translate-y-1/2 z-50">
          <SettingsMenu />
        </div>
        
        {/* Title - below logo */}
        <div className="w-full mt-1.5">
          <h1 className="font-semibold text-[18px] text-white -mt-2 text-center leading-tight">
            Instructor Assistant
          </h1>
        </div>
      </div>
    </header>
  );
}
