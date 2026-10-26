'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu } from 'antd';
import { Sparkles } from 'lucide-react';

const navItems = [
  { name: 'Mission', href: '/' },
  { name: 'Tutor', href: '/chat' },
  { name: 'Architecture', href: '/about' },
];

export default function Navbar() {
  const pathname = usePathname();

  return (
    <nav className="fixed top-0 w-full z-50 flex items-center justify-between gap-4 px-6 py-3 glass border-b-0">
      <Link href="/" className="flex items-center gap-2 group shrink-0 text-white! hover:text-white!">
        <div className="bg-gradient-to-tr from-indigo-500 to-purple-500 p-1.5 rounded-lg group-hover:scale-110 transition-transform duration-300">
            <Sparkles size={18} className="text-white" fill="white" />
        </div>
        {/* Wordmark hidden on phones so the three nav items fit on one line */}
        <span className="font-bold text-xl tracking-tight max-sm:sr-only">
          Cerebrix
        </span>
      </Link>

      <Menu
        mode="horizontal"
        selectedKeys={[pathname]}
        disabledOverflow
        className="border-b-0! min-w-0"
        items={navItems.map((item) => ({ key: item.href, label: <Link href={item.href}>{item.name}</Link> }))}
      />
    </nav>
  );
}
