import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';
import '@/features/office/office.css';
import '@/features/office3d/office3d.css';
export const metadata: Metadata = {
  title: 'Lazy Agents — AI Office',
  description: 'Browser controls for the authoritative local AI Office backend',
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <Link href="/">Lazy Agents</Link>
          <span>Your AI team, always on.</span>
        </header>
        {children}
      </body>
    </html>
  );
}
