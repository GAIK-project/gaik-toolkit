# GAIK Documentation Website

Documentation site for the GAIK toolkit, built with [Fumadocs](https://fumadocs.dev) and Next.js.

**Live site:** [gaik-project.github.io/gaik-toolkit](https://gaik-project.github.io/gaik-toolkit/)

## Development

```bash
pnpm install    # Install dependencies
pnpm dev        # Start dev server at localhost:3000
pnpm build      # Build static site to ./out
```

## Adding/Editing Documentation

Documentation files are in `content/docs/` as MDX files:

```mdx
---
title: Page Title
description: Brief description
---

Your content here with **markdown** and React components.
```

### Navigation Order

Control page order with `meta.json` in each folder:

```json
{
  "title": "Section Name",
  "pages": ["index", "page1", "page2"]
}
```

## Project Structure

```
website/
├── app/[[...slug]]/page.tsx    # Dynamic page renderer
├── content/docs/               # MDX documentation files
├── lib/source.ts               # Content loader config
├── public/                     # Static assets (logos, images)
└── next.config.mjs             # Next.js config (static export)
```

## Deployment

The site is automatically deployed to GitHub Pages when changes are pushed to `main` branch in the `website/` folder.

See `.github/workflows/pages.yml` for the deployment workflow.

## Learn More

- [Fumadocs Documentation](https://fumadocs.dev)
- [GAIK Toolkit on PyPI](https://pypi.org/project/gaik/)
