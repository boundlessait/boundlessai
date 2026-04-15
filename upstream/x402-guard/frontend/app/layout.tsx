import type { Metadata, Viewport } from "next";
import "./globals.css";
import SidebarLayout from "@/components/SidebarLayout";
import ErrorBoundary from "@/components/ErrorBoundary";

export const metadata: Metadata = {
  title: "x402guard — terminal",
  description: "AI Agent Spending Firewall",
};
export const viewport: Viewport = { themeColor: "#080808" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="icon"
          href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⬛</text></svg>" />
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            var SUPPRESS = ['MetaMask','chrome-extension','moz-extension','Failed to connect','inpage.js','ethereum','okxwallet'];
            function isSuppressed(msg) {
              if (!msg) return false;
              var s = String(msg);
              return SUPPRESS.some(function(p){ return s.indexOf(p) !== -1; });
            }
            window.addEventListener('error', function(e) {
              if (isSuppressed(e.message) || isSuppressed(e.filename)) { e.stopImmediatePropagation(); e.preventDefault(); return false; }
            }, true);
            window.addEventListener('unhandledrejection', function(e) {
              if (isSuppressed(e.reason && e.reason.message)) { e.stopImmediatePropagation(); e.preventDefault(); return false; }
            }, true);
          })();
        ` }} />
      </head>
      <body>
        <ErrorBoundary>
          <SidebarLayout>{children}</SidebarLayout>
        </ErrorBoundary>
      </body>
    </html>
  );
}
