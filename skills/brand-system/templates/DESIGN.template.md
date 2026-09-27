---
# Product-level design system. Read by brand-system/scripts/brand.py - see
# references/design-md-format.md for the exact subset the tools understand.
name: 'Product name'
description: 'One sentence: what the product is and how its surfaces should feel.'
colors:
  # Brand ramp + semantic colours + neutrals. Copy values from the frontend verbatim
  # and record where they came from under `provenance`.
  primary-50: '#EFF6FF'
  primary-600: '#2563EB'
  primary-800: '#1E40AF'
  primary-950: '#172554'
  accent-600: '#DB2777'
  success-600: '#16A34A'
  warning: '#F59E0B'
  danger: '#DC2626'
  info: '#0284C7'
  white: '#FFFFFF'
  surface-canvas: '#F8FAFC'
  surface-card: '#FFFFFF'
  surface-inset: '#F1F5F9'
  border: '#E2E8F0'
  gray-100: '#F1F5F9'
  gray-400: '#94A3B8'
  gray-600: '#475569'
  gray-900: '#0F172A'
typography:
  body:
    fontFamily: 'system-ui, sans-serif'
    fontSize: '1rem'
    fontWeight: 400
    lineHeight: 1.6
  headline:
    fontFamily: 'system-ui, sans-serif'
    fontSize: 'clamp(24px, 4vw, 32px)'
    fontWeight: 600
    lineHeight: 1.3
rounded:
  small: '4px'
  medium: '8px'
  large: '16px'
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
    success: '{colors.success-600}'
    warning: '{colors.warning}'
    danger: '{colors.danger}'
    info: '{colors.info}'
  dark:
    canvas: '{colors.primary-950}'
    surface: '{colors.gray-900}'
    inset: '{colors.primary-800}'
    ink: '{colors.gray-100}'
    muted: '{colors.gray-400}'
    border: '{colors.primary-800}'
    primary: '{colors.primary-50}'
    primary-strong: '{colors.white}'
    primary-soft: '{colors.primary-800}'
    on-primary: '{colors.primary-950}'
    accent: '{colors.accent-600}'
    success: '{colors.success-600}'
    warning: '{colors.warning}'
    danger: '{colors.danger}'
    info: '{colors.info}'
  # Optional (defaults in brackets): per scheme success-ink / warning-ink / danger-ink /
  # info-ink [the base role] - a darker EXISTING step that passes 4.5:1 as text;
  # shadow-sm / shadow-md [none] and wash [var(--ds-canvas)], shared or per scheme, built
  # only from {colors.x} refs; font-latin [font-body].
  font-body: '{typography.body}'
  font-display: '{typography.headline}'
  font-mono: 'ui-monospace, Consolas, Monaco, monospace'
  radius-sm: '{rounded.small}'
  radius-md: '{rounded.medium}'
  radius-lg: '{rounded.large}'
provenance:
  colors: 'repo:ref:path the colours were lifted from'
---

# Design System: Product name

<!-- CONFLICTS -->

This is the **product-level** design system: the brand every app and every generated
artifact shares. App-level systems (layout shells, component specs, navigation) live in
each app's own DESIGN.md and are not repeated here.

## Overview

**North star:** one sentence naming the feeling every surface should produce.

What the brand is, in a paragraph. What it deliberately is not.

## Colours

The palette in one sentence, then each group: what it is for and what it is never for.

- **Primary** - the house colour.
- **Accent** - the one colour allowed to disagree with the primary.
- **Semantic** - success, warning, danger, info: states only, never decoration.
- **Neutrals and surfaces** - canvas, card, inset, border, ink, muted.

**Dark scheme.** Artifacts support a dark scheme by mapping each role onto an existing
ramp token (see `artifact.dark`). No colour exists only for dark mode.

## Typography

Families, the scripts each covers, weights embedded for documents, line-height floors.

## Shape

The radius ladder and which rung documents use for chips, notices and cards.

## Elevation

How depth is expressed - and what documents do instead of shadows when printed.

## Voice in artifacts

Who reads the generated documents and how they should sound. Which languages, which
digits, which calendar.

## Artifacts: documents, PDF, dashboards

- Every artifact inlines `brand/brand.css` between the BRAND markers and styles itself
  only through `var(--ds-*)` roles. Derived tints are `color-mix(in oklab, ...)` of roles.
- Charts use role colours and mixes of them - never a separate palette.
- PDFs print the light scheme with `print-color-adjust: exact`.
- Artifacts carry the product brand, not a customer's or tenant's identity.

## Do / Don't

### Do

- Do ...

### Don't

- Don't ...
