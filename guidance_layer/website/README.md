# GAIK Documentation Website

Documentation site for the GAIK toolkit, built with [Fumadocs](https://fumadocs.dev) and Next.js.

**Live site:** [gaik-project.github.io/gaik-toolkit](https://gaik-project.github.io/gaik-toolkit/)

## Development

```bash
pnpm install    # Install dependencies
pnpm dev        # Start dev server at localhost:3000/gaik-toolkit
pnpm build      # Build static site to ./out
```

The site is served under the `/gaik-toolkit` base path (see `next.config.mjs`), in development as well as on GitHub Pages.

## Adding/Editing Documentation

Documentation files are in `content/docs/` as MDX files:

```mdx
---
title: Page Title
description: Brief description
---

Your content here with **markdown** and React components.
```

A file `content/docs/<path>.mdx` is published at `https://gaik-project.github.io/gaik-toolkit/<path>/`, with no `docs` segment (`content/docs/toolkit/software-components.mdx` becomes `/gaik-toolkit/toolkit/software-components/`, and a folder's `index.mdx` becomes the folder URL). Link between pages with site paths such as `/toolkit/software-components`; the base path is added for you.

Pages can also be edited in the browser with [Pages CMS](https://app.pagescms.org), configured in `.pages.yml` at the repository root. Saving commits to the branch you opened, and a save on `main` triggers the deployment below.

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
guidance_layer/website/
├── app/[[...slug]]/page.tsx    # Dynamic page renderer
├── content/docs/               # MDX documentation files
├── lib/source.ts               # Content loader config
├── lib/layout.shared.tsx       # Header links (GitHub, PyPI, Toolkit Demo) and sidebar footer
├── public/                     # Static assets (logos, images)
└── next.config.mjs             # Next.js config (static export)
```

## Deployment

The site is automatically deployed to GitHub Pages when changes are pushed to `main` branch in the `guidance_layer/website/` folder.

See `.github/workflows/pages.yml` for the deployment workflow.

## Learn More

- [Fumadocs Documentation](https://fumadocs.dev)
- [GAIK Toolkit on PyPI](https://pypi.org/project/gaik/)
