---
name: 'Todo'
description: 'A calm, get-it-done task tracker. Every surface reads as quick and uncluttered.'
colors:
  primary: '#16A34A'
  primary-50: '#F0FDF4'
  primary-100: '#DCFCE7'
  primary-200: '#BBF7D0'
  primary-300: '#86EFAC'
  primary-400: '#4ADE80'
  primary-500: '#22C55E'
  primary-600: '#16A34A'
  primary-700: '#15803D'
  primary-800: '#166534'
  primary-900: '#14532D'
  primary-950: '#052E16'
  accent-400: '#38BDF8'
  accent-500: '#0EA5E9'
  accent-600: '#0284C7'
  success: '#16A34A'
  warning: '#F59E0B'
  danger: '#DC2626'
  info: '#0284C7'
  white: '#FFFFFF'
  surface-canvas: '#F7F8F7'
  surface-card: '#FFFFFF'
  surface-inset: '#EEF2EF'
  border: '#DDE3DE'
  gray-100: '#F1F3F1'
  gray-400: '#8A9490'
  gray-600: '#54605A'
  gray-800: '#2B332F'
  gray-900: '#1B2320'
typography:
  display:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    fontSize: 'clamp(28px, 4vw, 36px)'
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: '-0.01em'
  headline:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    fontSize: 'clamp(22px, 3vw, 28px)'
    fontWeight: 600
    lineHeight: 1.3
  title:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    fontSize: '1.125rem'
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    fontSize: '1rem'
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    fontSize: '0.875rem'
    fontWeight: 600
    lineHeight: 1.4
rounded:
  xsmall: '6px'
  small: '10px'
  medium: '16px'
  large: '24px'
spacing:
  1: '4px'
  2: '8px'
  3: '12px'
  4: '16px'
  6: '24px'
  8: '32px'
artifact:
  light:
    canvas: '{colors.surface-canvas}'
    surface: '{colors.surface-card}'
    inset: '{colors.surface-inset}'
    ink: '{colors.gray-900}'
    muted: '{colors.gray-600}'
    border: '{colors.border}'
    primary: '{colors.primary-600}'
    primary-strong: '{colors.primary-800}'
    primary-soft: '{colors.primary-50}'
    on-primary: '{colors.white}'
    accent: '{colors.accent-600}'
    success: '{colors.success}'
    warning: '{colors.warning}'
    danger: '{colors.danger}'
    info: '{colors.info}'
  dark:
    canvas: '{colors.primary-950}'
    surface: '{colors.gray-900}'
    inset: '{colors.primary-900}'
    ink: '{colors.gray-100}'
    muted: '{colors.gray-400}'
    border: '{colors.gray-800}'
    primary: '{colors.primary-400}'
    primary-strong: '{colors.primary-300}'
    primary-soft: '{colors.primary-900}'
    on-primary: '{colors.primary-950}'
    accent: '{colors.accent-400}'
    success: '{colors.success}'
    warning: '{colors.warning}'
    danger: '{colors.danger}'
    info: '{colors.info}'
  font-body: '{typography.body}'
  font-display: '{typography.display}'
  font-mono: 'ui-monospace, SFMono-Regular, Consolas, monospace'
  radius-sm: '{rounded.xsmall}'
  radius-md: '{rounded.small}'
  radius-lg: '{rounded.medium}'
provenance:
  colors: 'hand-authored (no frontend repo to extract from — this example has no web-app source)'
  typography: 'hand-authored'
  rounded: 'hand-authored'
  spacing: 'hand-authored'
---

# Design System: Todo

This is the **product-level** design system: the brand every app and every generated artifact
shares. This example has no frontend repo, so it was written by hand rather than extracted with
`brand.py extract` — a hub without a registered design source does the same.

## Overview

**North star:** finishing a task should feel light, never like paperwork.

Todo is plain and quick: one confident green, generous whitespace, no decoration that isn't also
information. It is not playful or gamified — the brand stays out of the way of the list.

## Colours

- **Primary** — a single green ramp (`primary-50`…`primary-950`). The house colour for actions,
  links, and the one "done" affordance.
- **Accent** — a sky blue, used sparingly for anything that should stand apart from primary (e.g. a
  "new" badge). It never appears on a primary action.
- **Semantic** — `success`, `warning`, `danger`, `info`: states only, never decoration. `success`
  intentionally shares the primary hue — completing a task *is* the brand's success state.
- **Neutrals and surfaces** — `canvas`, `card`, `inset`, `border`, `ink`, `muted`.

**Dark scheme.** Artifacts support a dark scheme by mapping each role onto an existing ramp token
(see `artifact.dark`) — no colour exists only for dark mode. Semantic roles without a distinct dark
tone (`success`, `warning`, `danger`, `info`) reuse their light value in both schemes.

## Typography

System font stacks only — no custom face to embed, so every artifact renders identically without a
font download and PDFs never need font subsetting. One family across `display`, `headline`,
`title`, `body`, and `label`; weight and size carry the hierarchy instead of a second face.

## Shape

A four-rung radius ladder (`xsmall`…`large`). Documents use `radius-sm` for chips and badges,
`radius-md` for notices and inputs, `radius-lg` for cards and modals.

## Voice in artifacts

Generated documents (the roadmap, the dashboard, release notes) are read by the team and, for
release notes, by users of the to-do app. English, left-to-right, Gregorian calendar.

## Artifacts: documents, PDF, dashboards

- Every artifact inlines `brand/brand.css` between the `BRAND` markers and styles itself only
  through `var(--ds-*)` roles. Derived tints are `color-mix(in oklab, …)` of roles.
- Charts use role colours and mixes of them — never a separate palette.
- PDFs print the light scheme with `print-color-adjust: exact`.

## Do / Don't

### Do
- Do use `primary-600` for the one primary action per screen or document.
- Do let `success` and `primary` be the same hue — it reinforces "done."

### Don't
- Don't introduce a second brand colour outside `accent`.
- Don't add a display face "just for the roadmap" — every artifact shares this one system stack.
