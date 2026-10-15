import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AntdRegistry } from "@ant-design/nextjs-registry";
import SmoothScroll from "@/src/components/SmoothScroll";
import Navbar from "@/src/components/Navbar";
import AntdProvider from "@/src/components/AntdProvider";

// Use Google Fonts instead of local files
const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "Cerebrix | AI Teaching Assistant",
    template: "%s | Cerebrix",
  },
  description: "Advanced AI Tutor for CS109",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} antialiased`}>
        {/* layer: antd's CSS goes in @layer antd, ordered against Tailwind's layers in globals.css */}
        <AntdRegistry layer>
          <AntdProvider>
            <SmoothScroll>
              <div className="flex flex-col min-h-screen">
                 <Navbar />
                 <main className="flex-grow pt-16">{children}</main>
              </div>
            </SmoothScroll>
          </AntdProvider>
        </AntdRegistry>
      </body>
    </html>
  );
}