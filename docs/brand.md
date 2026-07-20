# CareerOS Local brand system

CareerOS Local presents privacy as product quality, not as a warning label. The identity is
quiet, precise, and technical enough to feel trustworthy without looking like infrastructure
software.

## Logo

The open **C** represents a career path that can keep evolving. Its connected node is the local
core: the place where a person’s verified record remains under their control.

| Asset | Use |
| --- | --- |
| [`assets/careeros-lockup.svg`](assets/careeros-lockup.svg) | README, project pages, and wide editorial placements |
| [`site/careeros-mark.svg`](site/careeros-mark.svg) | Compact navigation and product-site placements |
| [`site/favicon.svg`](site/favicon.svg) | Browser favicon |
| [`../frontend/public/careeros.svg`](../frontend/public/careeros.svg) | Desktop interface and boot state |

The repository hero and Devpost thumbnail are native geometric compositions with tracked SVG
sources. Render their PNG delivery files deterministically after changing either source:

```text
node scripts/render_brand_assets.mjs
```

The renderer rejects external resources, embedded raster images, scripts, font-dependent text,
off-centre frames, asymmetric modules, and viewport overflow.

The desktop icons are generated from the SVG master with the pinned Tauri CLI. Run this from
the repository root whenever the master artwork changes:

```text
npm --prefix frontend run brand:icons
```

Do not edit the generated files under `frontend/src-tauri/icons/` by hand.

Keep the clear space around the mark at least equal to one quarter of its width. Do not recolor,
rotate, stretch, add effects inside the artwork, or place it on a background with insufficient
contrast.

## Name and voice

Use **CareerOS Local** on first reference and **CareerOS** when the context is already clear.
The preferred descriptor is **Private career intelligence, on your device.**

Product copy should be direct, calm, and evidence-led:

- Lead with what the person can accomplish.
- Explain privacy through concrete architecture rather than broad promises.
- Treat AI as optional assistance, never as an autonomous authority.
- Avoid invented performance claims, urgency language, or surveillance-adjacent terminology.

## Color

| Token | Hex | Role |
| --- | --- | --- |
| Carbon | `#101411` | Mark base and deep surfaces |
| Vault green | `#B9F27C` | Primary action, verified state, and path |
| Paper | `#F4F7F2` | High-emphasis text and connector |
| Slate | `#9EAAA2` | Supporting copy |
| Boundary | `#2B362F` | Structural outlines |
| Signal blue | `#82B9FF` | Focus and informational states |

Vault green should remain an accent rather than a field color. Paper on Carbon is the default
reading combination; Signal blue is reserved for focus and information so privacy and success
states retain their meaning.

## Accessibility

The mark is decorative whenever the adjacent wordmark already names the product. Standalone
logo placements need the accessible name “CareerOS Local.” Preserve the existing focus styles,
reduced-motion behavior, and text alternatives when adapting the identity.
