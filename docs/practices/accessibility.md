# Accessibility

**Target: WCAG 2.2 Level AA** for every screen, public page, email and generated
report. It is checked in CI and in review, not retrofitted.

Why it matters here, beyond doing the right thing:

- The **European Accessibility Act** applies to many consumer-facing digital
  services in the EU since 28 June 2025, transposed in Portugal by Decreto-Lei
  n.º 82/2022. Micro-enterprises providing services are exempt, but customers
  will ask, and becoming non-exempt should not mean a rebuild.
- A dashboard people check at 7am on a phone, half-awake, benefits from every
  rule below.

## Rules

### Perceivable

- **Contrast:** text ≥ 4.5:1 (≥ 3:1 for 18.66px bold / 24px regular and up); UI
  components, focus indicators and chart marks ≥ 3:1 against neighbours. Checked
  for every token pair in **both** themes.
- **Never colour alone:** statuses use icon + word (see design system); charts use
  direct labels, markers or patterns in addition to colour; links in text are
  underlined.
- **Text alternatives:** meaningful images have `alt`; decorative ones `alt=""` /
  `aria-hidden`. Every chart has a text summary and a "View as table" option.
  Social post previews show the alt text the user wrote (and the composer
  prompts for alt text on every image it will publish).
- **Reflow:** usable at 320 CSS px wide and at 400% zoom with no two-dimensional
  scrolling (data tables may scroll horizontally inside their own region).
- **Text spacing and resize:** layout survives 200% text size and WCAG text-spacing
  overrides; no fixed-height text containers.

### Operable

- **Keyboard:** everything works with keyboard alone, in a logical order. No
  keyboard traps; dialogs trap focus intentionally and release it on close.
- **Focus visible:** a 2px `focus-ring` token outline with offset, never removed;
  focused element never fully hidden by sticky headers (WCAG 2.2 2.4.11).
- **Skip link** to main content on every page; landmarks (`header`, `nav`,
  `main`, `aside`) used once each and labelled where repeated.
- **Target size:** pointer targets ≥ 24×24 CSS px (2.2 SC 2.5.8); aim for 44×44
  on touch layouts.
- **Dragging alternatives:** every drag (Kanban cards, calendar posts, dashboard
  tiles) has a non-drag alternative — a "Move to…" menu or arrow-key reordering
  (2.2 SC 2.5.7).
- **Timing:** no session timeout without a warning and an option to extend;
  carousels and auto-refresh can be paused.
- **Shortcuts:** single-key shortcuts can be turned off or remapped; `⌘K` /
  `Ctrl K` command palette is the primary shortcut.
- **Motion:** respect `prefers-reduced-motion`; nothing flashes more than 3 times
  per second.

### Understandable

- `lang` set on `<html>` and on any passage in another language (Portuguese UI,
  post previews in other languages).
- Labels and instructions for every input; errors identify the field and say how
  to fix it; required fields marked in text, not just `*`.
- **Accessible authentication** (2.2 SC 3.3.8): no cognitive tests to sign in;
  password managers and paste allowed; passkeys supported.
- **Redundant entry** (2.2 SC 3.3.7): don't make people re-type what they already
  gave in the same flow (e.g. the setup wizard remembers values between steps).
- Consistent navigation and consistent help location (2.2 SC 3.2.6).

### Robust

- Native HTML elements first (`button`, `a`, `input`, `select`, `table`, `dialog`).
  ARIA only when no native element fits, and then follow the APG pattern.
- Radix primitives for complex widgets (menu, combobox, tabs, dialog, tooltip).
- Dynamic updates that matter are announced in a polite live region ("Post
  scheduled", "3 new alerts"); urgent failures use `role="alert"` sparingly.
- Charts: SVG with `role="img"` + `aria-label` summary, or a described figure with
  the data table as the accessible alternative.

## Emails and generated reports

- Semantic HTML emails (headings, `role="presentation"` layout tables), real text
  not images of text, 14px+ body, sufficient contrast, descriptive link text, a
  plain-text part.
- PDF exports (if added) are tagged PDFs with reading order and alt text.

## Component checklist

Before a component is merged:

- [ ] Native element or Radix primitive used
- [ ] Accessible name for every control (visible label preferred)
- [ ] Full keyboard support per the APG pattern; visible focus
- [ ] States exposed: `aria-expanded`, `aria-selected`, `aria-pressed`,
      `aria-invalid`, `aria-busy` as relevant
- [ ] Tokens only; contrast checked in light and dark
- [ ] Works at 320px and 200% text
- [ ] Reduced-motion respected
- [ ] axe: zero violations in its Storybook / `/dev/ui` states

## Testing

| Layer | How | When |
|---|---|---|
| Lint | `eslint-plugin-jsx-a11y` | Every save / CI |
| Unit | Testing Library queries by role and name (`getByRole('button', { name })`) — if you cannot query it by role, users of assistive tech cannot find it either | Every component test |
| Automated | `@axe-core/playwright` on every key route in both themes | CI, required |
| Manual keyboard | Tab through the changed flow end to end | Every UI PR |
| Screen reader | NVDA + Firefox/Chrome on Windows; VoiceOver + Safari on macOS/iOS; TalkBack on Android | Each new flow and before releases |
| Zoom/reflow | 400% zoom, 320px viewport | Each new layout |

Automated tools catch roughly a third of issues; the manual passes are not
optional.

## Statement

Publish an accessibility statement (`/accessibility`) with the conformance level,
known exceptions and a contact for problems, reviewed every release.
