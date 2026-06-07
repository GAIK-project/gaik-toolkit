import defaultMdxComponents from 'fumadocs-ui/mdx';
import { ImageZoom } from '@/components/mdx/image-zoom-client';
import { Mermaid } from '@/components/mdx/mermaid';
import type { MDXComponents } from 'mdx/types';

// use this function to get MDX components, you will need it for rendering MDX
export function getMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    Mermaid,
    ImageZoom,
    ...components,
  };
}
