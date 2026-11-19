# STACKLOOM brand

## Name and line

STACKLOOM, always in capitals as a wordmark; "Stackloom" is fine in running text.
Line: "One workspace. Every project. Complete control."

## The mark

Three staggered horizontal layers (the development stack) and two vertical threads
(the loom). Each thread passes over one layer and under the next, and breaks where
it goes under, so the weave reads even in one colour. It is drawn on a 32-unit grid:
layers 3.4 units thick, threads 2.8, round caps. `scripts/brand.py` is the source of
every file below; change the mark there and run `python scripts/brand.py --png`.

| File | Use |
|---|---|
| `assets/logo/stackloom-logo-light.svg` | primary logo with wordmark, light backgrounds |
| `assets/logo/stackloom-logo-dark.svg` | primary logo on a dark background |
| `assets/logo/stackloom-logo-mono.svg` | one colour (takes `currentColor`) |
| `assets/logo/stackloom-symbol.svg` | symbol alone, light backgrounds |
| `assets/logo/stackloom-symbol-dark.svg` | symbol alone, dark backgrounds |
| `assets/logo/stackloom-symbol-mono.svg` | symbol in one colour |
| `assets/icons/stackloom-app-icon.svg` | application icon (burgundy tile) |
| `assets/icons/favicon.svg` | browser tab icon (also in `frontend/public`) |
| `*-<size>.png` | PNG exports: app icon 16–1024 px, symbol 64–512 px, logos 416 and 832 px wide |

Keep clear space of at least one layer's length (about a quarter of the symbol's
width) around the logo. Do not recolour the threads and layers to the same colour
except in the mono version, rotate the mark, or add effects.

The wordmark is set in Inter Bold (falling back to the system sans) with 0.12 em
letter spacing. The SVGs use live text; outline it in a vector editor before
sending the logo to print.

## Colour

From the Archive palette (`app-color-palettes` skill), with the status colours chosen
for STACKLOOM.

| Role | Light | Dark |
|---|---|---|
| Ink navy (layers, text, sidebar) | `#1b2a44` | `#e7e9ee` |
| Burgundy (threads, app tile, one standout per view) | `#7b2236` | `#e09aaa` |
| Accent (buttons, links) | `#1f3a68` | `#9db8e8` |
| Stone (page) | `#f2f1ee` | `#14161a` |
| Borders | `#e5e7ef` | `#34373d` |
| Muted text | `#636c81` | `#80899d` |

Status colours. The hex values are used as fills (status dots, bars, graph nodes);
text uses the darker shade beside it so it passes WCAG AA on light and tinted
backgrounds.

| Meaning | Fill | Text (light) | Text (dark) |
|---|---|---|---|
| Success, running | `#16A36A` | `#117b50` | `#18b173` |
| Warning, pending | `#E6A23C` | `#956113` | `#e6a23c` |
| Error, stopped | `#DC5757` | `#cf2b2b` | `#e37979` |
| Information | `#4285D4` | `#2a6dbb` | `#659cdc` |

## Where it appears

Dashboard header and sign-in page, favicon and Apple touch icon, the CLI welcome
lines (`stackloom` and `stackloom status`), the README, the PyPI project page (the
README is its description) and the Homebrew tap's README.

© 2026 Nafees Mansoor (<https://www.nafees.info>)
