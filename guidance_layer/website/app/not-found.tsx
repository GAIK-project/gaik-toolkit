import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex items-center justify-center min-h-[100dvh]">
      <div className="max-w-md space-y-8 p-4 text-center">
        <div className="flex justify-center">
          <p className="text-6xl font-bold text-primary tracking-tight">😭</p>
        </div>
        <h1 className="text-4xl font-extrabold text-primary tracking-tight">
          Oh no!
          <br />
          This page is lost.
        </h1>
        <p className="text-lg text-muted-foreground">
          It looks like the page you were looking for doesn&apos;t exist. Maybe
          it was moved, or perhaps it never existed at all...
        </p>
        <Link
          href="/"
          className="max-w-48 mx-auto flex justify-center py-2 px-4 border border-gray-300 rounded-full shadow-xs text-sm font-medium text-gray-700 bg-white hover:bg-gray-100 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-black/50"
        >
          Take me home
        </Link>
      </div>
    </div>
  );
}
