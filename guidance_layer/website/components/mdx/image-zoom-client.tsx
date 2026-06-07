'use client';

import dynamic from 'next/dynamic';
import type { ComponentProps } from 'react';

// ImageZoom uses medium-zoom which references the browser `Element` global at
// module initialisation time. That crashes during static prerendering (SSR).
// Wrapping with dynamic + ssr:false defers the import to the browser.
const ZoomInner = dynamic(
  () => import('fumadocs-ui/components/image-zoom').then((m) => m.ImageZoom),
  { ssr: false },
);

export function ImageZoom(props: ComponentProps<'img'>) {
  return <ZoomInner {...props} />;
}
