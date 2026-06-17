# Documentation Website Reference

Documentation site for the GAIK toolkit at `guidance_layer/website/`, built with Fumadocs and Next.js.

**Live:** https://gaik-project.github.io/gaik-toolkit/

## Contents
- [Tech Stack](#tech-stack)
- [Dev Commands](#dev-commands)
- [Project Structure](#project-structure)
- [Content Map](#content-map)
- [Adding and Editing Pages](#adding-and-editing-pages)
- [Navigation](#navigation)
- [Deployment](#deployment)

## Tech Stack

- **Framework:** Fumadocs 16.5, Next.js 16
- **Package manager:** pnpm (NOT bun)
- **Styling:** Tailwind CSS v4
- **Content:** MDX files with frontmatter
- **Plugins:** Mermaid diagrams (via `source.config.ts`)
- **Output:** Static export to `./out` directory

## Dev Commands

```bash
cd guidance_layer/website

pnpm install    # Install dependencies
pnpm dev        # Start dev server at localhost:3000
pnpm build      # Build static site to ./out
```

## Project Structure

```
guidance_layer/website/
├── app/[[...slug]]/page.tsx    # Dynamic page renderer
├── content/docs/               # MDX documentation files
│   ├── meta.json               # Root navigation order
│   ├── index.mdx               # Toolkit overview
│   ├── toolkit/                # Implementation layer docs
│   │   ├── meta.json
│   │   ├── software-components.mdx
│   │   ├── software-modules.mdx
│   │   └── no-code-assets.mdx
│   ├── evaluation-layer/       # Evaluation layer docs
│   │   ├── meta.json
│   │   ├── index.mdx
│   │   ├── value-evaluation-framework.mdx
│   │   └── *-eval.mdx
│   └── use-cases/              # Use case documentation
│       ├── meta.json
│       └── *.mdx
├── lib/source.ts               # Content loader config
├── source.config.ts            # Fumadocs + Mermaid plugin config
├── public/                     # Static assets (logos, images)
└── next.config.mjs             # Next.js config (static export)
```

## Content Map

### Root pages (`content/docs/`)
| File | Topic |
|------|-------|
| `index.mdx` | Toolkit overview, knowledge processes, layer architecture |
| `strategy-layer.mdx` | Use case selection, value evaluation |
| `business-layer.mdx` | Use case definition, workflows |
| `guidance-layer.mdx` | Implementation process, getting started |
| `requirements-layer.mdx` | Requirements capture and specs |
| `security-compliance-layer.mdx` | Security and compliance |
| `demo.mdx` | Demo app feature descriptions |
| `contact.mdx` | Contact information |

### Toolkit docs (`content/docs/toolkit/`)
| File | Topic |
|------|-------|
| `software-components.mdx` | Building blocks documentation |
| `software-modules.mdx` | Software modules documentation |
| `no-code-assets.mdx` | Prompt templates and agent skills |

### Evaluation layer (`content/docs/evaluation-layer/`)
| File | Topic |
|------|-------|
| `index.mdx` | Evaluation layer overview |
| `value-evaluation-framework.mdx` | Business-value evaluation framework |
| `transcription-eval.mdx` | Transcription accuracy evaluation |
| `extraction-eval.mdx` | Extraction accuracy evaluation |
| `llm-judge.mdx` | LLM-as-judge validation |
| `llm-judge-benchmark.mdx` | LLM-judge prompt benchmark |
| `rag-eval.mdx` | RAG evaluation |
| `report-writing-eval.mdx` | Report quality evaluation |
| `translation-eval.mdx` | Translation quality evaluation |

### Use cases (`content/docs/use-cases/`)
| File | Topic |
|------|-------|
| `incident-reporting.mdx` | Cross-cutting safety/incident management |
| `dental-transcription-close-captioning.mdx` | Audio/video transcription for learning |
| `semantic-dental-video-search.mdx` | Content-based video search |
| `dental-learning-assistant.mdx` | Educational support system |
| `construction-site-diary-creation.mdx` | Daily site activity logging |
| `purchase-order-processing.mdx` | PO to sales order automation |
| `report-writing.mdx` | Automated report generation |
| `sales-proposal-generation.mdx` | Proposal creation automation |
| `customer-onboarding-sales-assistant.mdx` | Sales support tool |

## Adding and Editing Pages

### Create a new page

1. Create `.mdx` file in the appropriate directory:

```mdx
---
title: Page Title
description: Brief description
---

Your content here with **markdown** and React components.
```

2. Add the page slug to the `meta.json` in the same directory (see Navigation below)

### Edit an existing page

Edit the `.mdx` file directly. Fumadocs supports standard markdown, JSX components, and Mermaid diagrams.

## Navigation

Page order is controlled by `meta.json` files in each directory.

**Root** (`content/docs/meta.json`):
```json
{
  "title": "Documentation",
  "pages": ["index", "strategy-layer", "business-layer", "toolkit",
            "guidance-layer", "requirements-layer", "security-compliance-layer",
            "use-cases", "demo", "contact"]
}
```

**Toolkit** (`content/docs/toolkit/meta.json`):
```json
{
  "title": "Implementation Layer",
  "pages": ["software-components", "software-modules", "evals", "no-code-assets"]
}
```

To add a page: add its slug (filename without `.mdx`) to the `pages` array.

## Deployment

Automatically deployed to GitHub Pages on push to `main` branch (changes in `guidance_layer/website/`).

Workflow: `.github/workflows/pages.yml`
