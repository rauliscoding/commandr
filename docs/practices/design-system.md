# Design system

Commandr is a tool people open to answer a question quickly: *is anything wrong,
what happened this week, what do I do next?* The design system serves that.
**Calm by default, loud only when something needs a decision.**

## Principles

1. **Start from what can be connected, not from an empty dashboard.** A screen
   with no data shows what would fill it and the one action that does it.
2. **One primary action per view.** If two things compete, one of them belongs
   elsewhere.
3. **Status is never colour alone.** Every state has an icon and a word.
4. **Numbers are honest.** Unknown is "—", not 0. Every figure says its period
   ("last 7 days") and its source on hover.
5. **Density is a setting, not a compromise.** Comfortable by default, compact on
   request, same components.
6. **Owned, not rented.** Components live in `frontend/src/components/ui/`, built
   on Radix primitives and Tailwind. We do not depend on a component library's
   release cycle.

---

## Foundations

### Tokens

All visual values are CSS custom properties in `frontend/src/styles/tokens.css`,
exposed to Tailwind through `@theme`. **Components reference tokens, never raw
values.** A hex colour or a `px` value in a component is a review finding.

Naming is semantic, not descriptive: `--color-surface`, not `--color-gray-50`.

| Group | Tokens |
|---|---|
| Surfaces | `surface`, `surface-raised`, `surface-sunken`, `overlay` |
| Text | `text`, `text-muted`, `text-subtle`, `text-inverse`, `text-link` |
| Borders | `border`, `border-strong`, `focus-ring` |
| Brand | `primary`, `primary-hover`, `primary-contrast` |
| Status | `ok`, `warn`, `fail`, `unknown`, `info` — each with `-bg`, `-fg`, `-border` |
| Data viz | `chart-1` … `chart-8` categorical; `seq-*` sequential; `div-*` diverging |

Light and dark themes redefine the same tokens under `[data-theme]`, defaulting to
`prefers-color-scheme`. Both themes must meet the contrast rules in
[accessibility.md](accessibility.md); verify each new token pair.

### Typography

- Family: system UI stack for text (`ui-sans-serif, system-ui, …`); a monospace
  stack for code, IDs, keys and numbers in tables (tabular figures:
  `font-variant-numeric: tabular-nums`).
- Scale (rem, 16px root): `xs 0.75` · `sm 0.875` · `base 1` · `lg 1.125` · `xl 1.25` ·
  `2xl 1.5` · `3xl 1.875`. Body is `base`; tables may use `sm`; nothing
  interactive below `sm`.
- Line height 1.5 for body, 1.25 for headings. Max line length ~70ch for prose.
- Sentence case everywhere — headings, buttons, menu items.

### Spacing, radius, elevation

- 4px base grid: `0.5 1 1.5 2 3 4 6 8 12 16` (×4px). Use the scale, not arbitrary values.
- Radius: `sm 4px` inputs/chips · `md 8px` cards/buttons · `lg 12px` dialogs.
- Elevation: three shadows (`raised`, `overlay`, `modal`). Borders do most of the
  separation work; shadows are for things that float.

### Motion

- Durations: `fast 120ms`, `base 200ms`, `slow 320ms`; ease-out for entering,
  ease-in for leaving.
- Motion explains a change (a panel arriving, a row being added). It never
  decorates.
- `prefers-reduced-motion: reduce` turns transitions into instant changes. Required.

### Iconography

- One icon set: **Lucide**, 16px inline / 20px in buttons / 24px standalone,
  stroke 1.75.
- Decorative icons get `aria-hidden="true"`. An icon-only button gets an
  `aria-label` and a tooltip with the same words.
- Integration logos are the provider's official mark, unmodified, on a neutral
  tile, with the provider name as text beside or below it.

---

## Status language

The same five states everywhere — checks, connections, posts, syncs:

| State | Token | Icon | Word | Meaning |
|---|---|---|---|---|
| ok | `ok` | `CircleCheck` | Healthy / Connected / Published | Nothing to do |
| warn | `warn` | `TriangleAlert` | Degraded / Attention | Look soon |
| fail | `fail` | `CircleX` | Failing / Disconnected / Failed | Decide now |
| unknown | `unknown` | `CircleHelp` | No data / Not checked | We cannot say — never shown as ok |
| info | `info` | `Info` | Scheduled / Syncing | In progress |

The `StatusBadge` component renders icon + word; colour is the third cue, never
the only one.

---

## Layout

- **App shell:** left navigation (collapsible to icons), top bar with
  organization/project switcher, search (`⌘K` / `Ctrl K`), notifications and
  account. Content max width 1440px; prose pages 720px.
- **Navigation order** follows the product areas: Home · Health · Social · Email ·
  Analytics · Money · Board · Integrations · Settings.
- **Breakpoints:** `sm 640` · `md 768` · `lg 1024` · `xl 1280`. Works at 320px wide
  with no horizontal scroll (WCAG reflow); navigation becomes a drawer below `lg`.
- **Page anatomy:** title + one-line description → primary action (top right) →
  filters → content. Breadcrumbs only when a page is more than two levels deep.

---

## Patterns

### Catalogue-first onboarding

The first screen of a new project **is** the integration catalogue
(`features/catalogue`). Full flow in
[onboarding-and-catalogue.md](../product/onboarding-and-catalogue.md). Visual rules:

- Cards in a responsive grid, grouped by category with a sticky category filter
  and a search box.
- Each card: logo, name, one-line "what it unlocks", setup time ("~2 min"),
  requirement chips ("Needs a Meta app", "Free"), and its state
  (`Connect` / `Connected ✓` / `Needs attention`).
- A **"Recommended first"** row on top: the three connections that produce useful
  data fastest for this kind of project.
- A progress strip: "2 of 5 recommended connected", never a percentage of the
  whole catalogue.

### Setup wizard

- A right-hand sheet (desktop) or full screen (mobile), never a new page, so the
  catalogue stays as context.
- Numbered steps with the current one expanded; each step says what the user does,
  where (link opens in a new tab, marked as such), and how we will know it worked.
- Copyable values (callback URLs, keys) use the `CopyField` component: read-only
  input + copy button + "Copied" live announcement.
- The last step is **"Waiting for first data"** with a live indicator, then the
  first values themselves. Never end a wizard on "Done!" with nothing to show.

### Empty states

Every list, chart and dashboard has one. It says: what would be here, why it is
empty, and the single action that fills it ("Connect Google Analytics to see
traffic here"). Illustration optional; the action is not.

### Data display

- **KPI tile:** label, value, period, delta vs previous period with direction
  icon and sign (`+12%`), sparkline optional. Delta colour follows meaning, not
  direction (more errors is red even though it is "up").
- **Charts:** line for time series, bar for comparisons, never pie for more than
  three slices. Axis labels and units always; legend only with ≥2 series. Every
  chart has a "View as table" toggle (accessibility and export).
- **Tables:** sticky header, sortable columns announce their sort state, numbers
  right-aligned with tabular figures, row actions in a trailing menu, bulk
  actions in a floating bar once rows are selected.
- **Time:** relative for under 24h ("12 min ago") with the absolute time in a
  tooltip; absolute in the organization's time zone otherwise.

### Forms

- Label above the field, always visible (no placeholder-as-label). Help text below
  the label, errors below the field, linked by `aria-describedby`.
- Validate on blur and on submit; on submit failure, focus the first invalid field
  and show a summary at the top for long forms.
- Destructive actions: secondary-styled trigger, confirmation dialog that names
  the object and the consequence, and for irreversible ones a typed confirmation.

### Feedback

- Toasts for completed background actions only ("Post scheduled for Fri 09:00").
  Errors that need action stay on the page, next to the cause.
- Long operations show progress and can be left: "We'll email you when the import
  finishes."

### Kanban board

- Columns are lists, cards are list items; drag and drop has a keyboard
  equivalent (select card → move with arrow keys / "Move to…" menu) and announces
  moves in a live region.
- A card linked to an alert, post or campaign shows that object's status badge.

---

## Voice and copy

- Plain, direct, second person. "Connect your Instagram account", not "Instagram
  integration configuration".
- Say what happened and what to do: "Instagram stopped accepting our token.
  Reconnect to keep publishing." — never "Error 190".
- No blame, no exclamation marks, no jargon a non-developer would not know
  (developer-only screens excepted).
- Numbers and dates in the user's locale; currency with its symbol.
- Every string goes through i18n from day one (`en` first, `pt` next). No string
  concatenation for sentences.

---

## Adding a component

1. Check whether an existing component or variant covers it.
2. Build on a Radix primitive when one exists (Dialog, Popover, Menu, Tabs, Select,
   Tooltip…) — they solve focus and ARIA correctly.
3. Tokens only; variants with `class-variance-authority`.
4. Document it in Storybook (or the `/dev/ui` route) with every state: default,
   hover, focus, disabled, loading, error, empty, long content, RTL-safe text.
5. Pass the [accessibility checklist](accessibility.md#component-checklist) and an
   axe scan.
