# Design

> Status: **decided** (2026-11-15). How the web app looks: the dashboard, login, invitations and the magic-link form. Tools: [tech.md](tech.md). Code: `web/app/globals.css` (tokens), `web/components/ui/` (components).

The people using Argos are a patient living with dementia and the family around them. The interface should feel calm, warm and trustworthy, and never busy. Plain words, generous space, one clear action per screen.

## Stack

- **Tailwind CSS v4** in `web/` (`tailwindcss`, `@tailwindcss/postcss`, `web/postcss.config.mjs`). `@import "tailwindcss"` and every token live in `web/app/globals.css`, inside `@theme`. Tailwind's default color palette is turned off (`--color-*: initial`), so only the tokens below exist.
- **shadcn/ui** for components. The source is copied into `web/components/ui/` and themed with the tokens; `cn()` is in `web/lib/utils.ts`. In use so far: `button`, `input`, `label`, `card`, `alert` (variants `default`, `danger`, and `warning` for gentle "please try again" notes such as a voice sample to re-record), `avatar`, `textarea`, `badge`.
- **Icons:** `lucide-react`, stroke width 1.75, 16–20 px, `aria-hidden` when next to a text label.
- **Fonts:** `next/font/google`, downloaded at build time and served from our own site (no runtime call to Google). **Source Serif 4** for headings (`font-serif`), **Source Sans 3** for body and UI (`font-sans`, the default).

## Colors ("Aegean")

Light mode only for the MVP. Components use token names only (`bg-canvas`, `text-ink`, `bg-primary`, `border-border-strong`…), never hex values. Contrast ratios are against the background named.

| Token | Hex | Use | Contrast |
|---|---|---|---|
| `canvas` | `#F7F5F0` | page background (warm off-white) | |
| `surface` | `#FFFFFF` | cards, inputs, dialogs | |
| `subtle` | `#EFECE5` | hover rows, table headers, empty states | |
| `border` | `#E3DED5` | card and divider borders | decorative |
| `border-strong` | `#948C80` | input borders | 3.3:1 on surface, 3.1:1 on canvas (WCAG 1.4.11) |
| `ink` | `#1F1D1A` | main text | 16.8:1 on surface, 15.4:1 on canvas |
| `muted` | `#5C574F` | secondary text | 7.2:1 on surface, 6.6:1 on canvas, 6.1:1 on subtle |
| `primary` | `#1E4D5C` | deep Aegean teal: primary buttons, links, focus ring, active nav | 9.3:1 on surface, 8.5:1 on canvas |
| `primary-hover` | `#173C48` | hover and pressed | 11.8:1 with white text |
| `primary-soft` | `#E4EEF0` | selected states, badges, soft backgrounds | `primary` text on it 7.8:1 |
| `on-primary` | `#FFFFFF` | text on `primary` and `danger` | 9.3:1 on primary |
| `accent` | `#8C6A2F` | warm bronze, used sparingly (e.g. the "patient" badge), never on buttons | 5.0:1 on surface; **4.2:1 on `primary-soft`, so don't put accent text on it** |
| `success` | `#2E6A4E` | saved, processed | 6.4:1 on surface |
| `warning` | `#8A5A12` | expiring invitation, low-quality voice sample | 5.9:1 on surface |
| `danger` | `#A33A2C` | terracotta: delete, errors | 6.6:1 with white text |
| `danger-soft` | `#F8EFEE` | background of error alerts | `danger` text on it 5.8:1 |
| `sidebar` | `#1A2B31` | dark "night sea" sidebar | |
| `sidebar-ink` | `#EDEAE3` | sidebar text; focus ring inside the sidebar | 12.2:1 on sidebar |
| `sidebar-muted` | `#A3A7A5` | inactive and disabled sidebar items | 6.0:1 on sidebar |
| `sidebar-active` | `#2F3E43` | sidebar hover, active item, divider | `sidebar-ink` on it 9.2:1 |

Every text pair meets WCAG AA: 4.5:1 for body text, 3:1 for large text and UI borders. Check a new pair before using it.

**Focus inside the sidebar:** the `primary` ring is only 1.6:1 on `sidebar`, so controls in the sidebar use a `sidebar-ink` ring instead.

## Type

- Base 16 px, line height 1.6. Nothing below 14 px.
- Headings in the serif: page title 28–32 px semibold (`text-3xl font-semibold`), section 20 px (`text-xl`).
- UI labels 14 px medium in the sans (`text-sm font-medium`).
- Sentence case everywhere; no all-caps headings.

## Spacing and shape

- 4 px grid (Tailwind's spacing scale). Content max width 1120 px. Generous whitespace.
- Radius: 10 px on cards and dialogs (`rounded-card`), 8 px on buttons and inputs (`rounded-control`), full circle on avatars (`rounded-full`).
- Depth comes from 1 px `border` lines. Cards may use the one soft shadow (`shadow-card`: `0 1px 2px rgb(31 29 26 / 0.06)`); nothing heavier.
- Focus: a visible 2 px ring with an offset on every interactive element (`focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`).
- Touch targets at least 44 px high (`min-h-11`).
- Motion: 150 ms ease-out on hover and focus only (Tailwind's default transition is set to that). `prefers-reduced-motion` turns transitions off.

## Layout

- **Dashboard shell** (`web/app/(dashboard)/layout.tsx` and `dashboard-shell.tsx`):
  - A fixed 240 px sidebar on `sidebar`, with the serif "Argos" wordmark and nav items (People, Invitations, Conversations) with lucide icons. An item whose page doesn't exist yet is shown disabled.
  - The signed-in user's name and **Log out** sit at the bottom of the sidebar.
  - On phones and tablets (below 1024 px) the sidebar becomes a top bar with a menu button.
  - The main area is on `canvas`, content up to 1120 px wide.
- **Page header** (`web/components/page-header.tsx`): serif title plus a one-line description in `muted`. Content goes in cards below it.
- **Login:** a centered card (max 400 px) on `canvas` with the serif wordmark, a one-line warm subtitle, the fields, and a full-width primary button. Errors show in an inline `danger` alert.
- **Empty states:** a card with a small icon in a `primary-soft` circle, a short serif heading and one warm sentence on what to do next.

## Dates

One format everywhere, pages and emails: **"15 November 2026"** (decided 2026-11-15; `web/lib/format.ts`). Times of day are shown in the viewer's own time zone (`web/components/local-time.tsx`).

## Words

Plain, warm, never corrective. Say what happened and what to do next ("That email and password don't match. Please try again."), not what the person did wrong. No jargon, no exclamation marks.

## Avoid

- Gradients (including gradient text), glassmorphism or blur, glow or neon.
- Purple, indigo or violet.
- Emoji in the UI, stock illustrations, decorative blobs.
- All-caps headings, centered marketing heroes on dashboard pages.
- More than one primary button per view.
- Hex values or Tailwind's default colors in components; use the tokens.

## Adding a shadcn component

1. From `web/`: `npx shadcn@latest add <component>`. `web/components.json` sends it to `web/components/ui/`.
2. Restyle it with the tokens: replace shadcn's names (`bg-background`, `text-foreground`, `text-muted-foreground`, `border-input`, `ring-ring`, `bg-destructive`, `bg-card`…) with ours (`bg-canvas`/`bg-surface`, `text-ink`, `text-muted`, `border-border-strong`, `outline-primary`, `bg-danger`, `bg-surface`). Use the focus ring and the `min-h-11` touch target above.
3. If the CLI adds CSS variables to `globals.css`, remove them; the tokens there are the only theme.
4. Check that each new text pair meets the contrast rules above.

`/plan` is an internal team page and keeps its own CSS module; it is not themed with these tokens.
