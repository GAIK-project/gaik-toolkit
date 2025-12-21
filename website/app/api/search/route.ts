import { source } from '@/lib/source';
import { createFromSource } from 'fumadocs-core/search/server';

// Staattinen cache GitHub Pagesille
export const revalidate = false;

export const { staticGET: GET } = createFromSource(source, {
  language: 'english',
});
