'use client';
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main>
      <h1>Project view could not load</h1>
      <p>
        The page failed to render. Backend execution continues independently.
      </p>
      <button onClick={reset}>Reload view</button>
    </main>
  );
}
