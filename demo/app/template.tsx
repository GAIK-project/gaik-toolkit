export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-6xl px-6 pt-24 pb-24 sm:px-8">
      {children}
    </main>
  );
}
