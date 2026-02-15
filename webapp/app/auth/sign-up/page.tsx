import { SignUpForm } from "@/components/sign-up-form";
import Link from "next/link";
import Image from "next/image";

export default function Page() {
  return (
    <div className="relative flex min-h-svh w-full items-center justify-center p-6 md:p-10">
      <div className="absolute inset-0 grid-background" />
      <div className="relative w-full max-w-sm">
        <div className="mb-8 text-center">
          <Link href="/" className="inline-flex items-center gap-2 mb-4">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-foreground">
              <Image
                src="/Logo.png"
                alt="Current logo"
                width={24}
                height={24}
                className="h-6 w-6 rounded-sm invert dark:invert-0"
                priority
              />
            </div>
            <span className="font-semibold text-foreground tracking-tight">Current</span>
          </Link>
        </div>
        <SignUpForm />
      </div>
    </div>
  );
}
