"use client";

type GlobalErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-forge-bg text-foreground">
        <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col items-start justify-center gap-4 px-6">
          <h1 className="text-2xl font-semibold">Something went wrong</h1>
          <p className="text-sm text-muted-foreground">
            The application hit an unexpected error. Please try again.
          </p>
          <button
            type="button"
            onClick={reset}
            className="rounded-md bg-orange-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-orange-400"
          >
            Retry
          </button>
          {error?.digest ? <p className="text-xs text-muted-foreground">Error ID: {error.digest}</p> : null}
        </main>
      </body>
    </html>
  );
}
