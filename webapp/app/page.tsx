import Link from "next/link";
import Image from "next/image";

export default function LandingPage() {
  return (
    <div className="relative min-h-screen bg-white overflow-hidden">
      {/* Gradient background */}
      <div className="absolute inset-0">
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(135deg, #a5d8d0 0%, #b8e0db 15%, #e8d5e8 35%, #f0c4d8 50%, #f2b0b0 65%, #f5c6aa 80%, #dcc4e8 100%)",
          }}
        />
        {/* Grid overlay */}
        <div
          className="absolute inset-0"
          style={{
            backgroundSize: "60px 60px",
            backgroundImage:
              "linear-gradient(to right, rgba(255,255,255,0.35) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.35) 1px, transparent 1px)",
          }}
        />
        {/* Soft vignette */}
        <div className="absolute inset-0 bg-gradient-to-b from-white/20 via-transparent to-white/30" />
      </div>

      {/* Content */}
      <div className="relative z-10 flex min-h-screen flex-col">
        {/* Nav */}
        <header className="flex items-center justify-between px-8 py-6 lg:px-16">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-black">
              <Image
                src="/Logo.png"
                alt="Matrix logo"
                width={18}
                height={18}
                className="h-[18px] w-[18px] rounded-sm invert"
                priority
              />
            </div>
            <span className="text-base font-semibold text-gray-900 tracking-tight">Matrix</span>
          </Link>
          <nav className="flex items-center gap-6 text-sm">
            <Link href="/features" className="text-gray-500 hover:text-gray-900 transition-colors">
              Dashboard
            </Link>
            <Link href="/auth/login" className="text-gray-500 hover:text-gray-900 transition-colors">
              Sign In
            </Link>
            <Link
              href="/features"
              className="rounded-full bg-black px-5 py-2 text-sm font-medium text-white hover:bg-gray-800 transition-colors"
            >
              Get Started
            </Link>
          </nav>
        </header>

        {/* Hero */}
        <main className="flex flex-1 items-center px-8 lg:px-16">
          <div className="w-full max-w-6xl mx-auto grid lg:grid-cols-2 gap-16 items-center">
            {/* Left: White card with content */}
            <div className="bg-white/90 backdrop-blur-sm rounded-3xl p-10 lg:p-14 shadow-xl shadow-black/5">
              <h1 className="text-4xl sm:text-5xl font-semibold leading-[1.1] tracking-tight text-gray-900">
                Your users ask.
                <br />
                <span className="text-gray-400">We ship.</span>
              </h1>

              <p className="mt-6 text-base text-gray-500 leading-relaxed max-w-md">
                Matrix monitors what your users are saying on social media, creates implementation plans, and delivers pull requests — autonomously.
              </p>

              <div className="flex items-center gap-4 mt-8">
                <Link
                  href="/features"
                  className="inline-flex items-center gap-2 rounded-full bg-black px-6 py-3 text-sm font-medium text-white hover:bg-gray-800 transition-colors"
                >
                  Get Started
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                  </svg>
                </Link>
                <Link
                  href="/auth/login"
                  className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-900 transition-colors"
                >
                  Learn more
                </Link>
              </div>
            </div>

            {/* Right: empty — the gradient + grid IS the visual */}
            <div className="hidden lg:block" />
          </div>
        </main>

        {/* Footer */}
        <footer className="flex items-center justify-between px-8 py-6 lg:px-16 text-xs text-gray-400">
          <span>&copy; 2025 Matrix</span>
          <div className="flex items-center gap-6">
            <Link href="#" className="hover:text-gray-600 transition-colors">Privacy</Link>
            <Link href="#" className="hover:text-gray-600 transition-colors">Terms</Link>
          </div>
        </footer>
      </div>
    </div>
  );
}
