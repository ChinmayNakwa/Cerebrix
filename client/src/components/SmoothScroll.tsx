'use client';
import { usePathname } from 'next/navigation';
import { ReactLenis } from 'lenis/react';

export default function SmoothScroll({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // The chat page scrolls inside its own panels, so Lenis is only overhead there.
  if (pathname.startsWith('/chat')) return <>{children}</>;

  return (
    <ReactLenis root>
      {children}
    </ReactLenis>
  );
}
