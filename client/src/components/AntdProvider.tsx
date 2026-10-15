'use client';
import { App, ConfigProvider, theme } from 'antd';

// Ant Design on the site's dark palette (see the @theme colors in globals.css).
// <App> provides message/modal hooks with this theme via App.useApp().
export default function AntdProvider({ children }: { children: React.ReactNode }) {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#6366f1',
          colorBgBase: '#050505',
          colorBgContainer: '#0f0f12',
          colorBgElevated: '#141418',
          colorBorder: 'rgba(255, 255, 255, 0.12)',
          colorBorderSecondary: 'rgba(255, 255, 255, 0.08)',
          borderRadius: 12,
          fontFamily: 'inherit',
        },
        components: {
          Menu: { itemBg: 'transparent', horizontalItemSelectedColor: '#ffffff', itemColor: '#a1a1aa', itemHoverColor: '#ffffff' },
        },
      }}
    >
      <App>{children}</App>
    </ConfigProvider>
  );
}
