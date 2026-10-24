---
name: Kinetic Grid
colors:
  surface: '#111417'
  surface-dim: '#111417'
  surface-bright: '#37393d'
  surface-container-lowest: '#0b0e11'
  surface-container-low: '#191c1f'
  surface-container: '#1d2023'
  surface-container-high: '#272a2d'
  surface-container-highest: '#323538'
  on-surface: '#e1e2e7'
  on-surface-variant: '#bac9cc'
  inverse-surface: '#e1e2e7'
  inverse-on-surface: '#2e3134'
  outline: '#849396'
  outline-variant: '#3b494c'
  surface-tint: '#00daf3'
  primary: '#c3f5ff'
  on-primary: '#00363d'
  primary-container: '#00e5ff'
  on-primary-container: '#00626e'
  inverse-primary: '#006875'
  secondary: '#ffd799'
  on-secondary: '#432c00'
  secondary-container: '#feb300'
  on-secondary-container: '#6a4800'
  tertiary: '#b1ffbf'
  on-tertiary: '#003918'
  tertiary-container: '#22ef7e'
  on-tertiary-container: '#006731'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#9cf0ff'
  primary-fixed-dim: '#00daf3'
  on-primary-fixed: '#001f24'
  on-primary-fixed-variant: '#004f58'
  secondary-fixed: '#ffdeac'
  secondary-fixed-dim: '#ffba38'
  on-secondary-fixed: '#281900'
  on-secondary-fixed-variant: '#604100'
  tertiary-fixed: '#62ff96'
  tertiary-fixed-dim: '#00e475'
  on-tertiary-fixed: '#00210b'
  on-tertiary-fixed-variant: '#005226'
  background: '#111417'
  on-background: '#e1e2e7'
  surface-variant: '#323538'
typography:
  headline-xl:
    fontFamily: Space Grotesk
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Space Grotesk
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Space Grotesk
    fontSize: 22px
    fontWeight: '700'
    lineHeight: 28px
    letterSpacing: 0em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 26px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 26px
  body-md:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  label-lg:
    fontFamily: Space Grotesk
    fontSize: 16px
    fontWeight: '700'
    lineHeight: 20px
    letterSpacing: 0.04em
  label-md:
    fontFamily: Space Grotesk
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.06em
  label-sm:
    fontFamily: Space Grotesk
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 14px
    letterSpacing: 0.08em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-desktop: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system is engineered for the high-friction physical realities of logistics, distribution hubs, and retail fulfillment centers. Built for frontline warehouse technicians operating in variable lighting—from dim storage racks to glare-heavy loading docks—the aesthetic blends **Modern Industrial Utilitarianism** with **High-Contrast Digital Precision**.

Key attributes:
- **Ergonomic & Glove-First:** Optimized for rapid, one-handed terminal and mobile PWA usage. Every interaction zone prioritizes high-confidence target areas and immediate physical thumb reach.
- **Instrumental & Functional:** Visuals mimic industrial diagnostic instruments rather than consumer software. Every border, contrast step, and signal glyph serves spatial orientation or parcel telemetry.
- **Rugged Resilience:** Dark mode is the primary operating canvas to minimize screen battery drain, prevent peripheral vision glare in poorly lit aisles, and create immediate pop for signal diagnostics.

## Colors

The palette operates on high-visibility functional zoning against deep, noise-free industrial surfaces. Color conveys operational state, proximity, and urgency without ambiguity:

- **Signal Cyan (`#00E5FF` - Primary):** The core active beacon state, telemetry pulses, dynamic ranging indicators, and focal touchpoints. High lumen emission ensures daylight and glare readability.
- **Alert Amber (`#FFB300` - Secondary):** In-transit states, threshold warnings, missing packet queries, and intermediate urgency queues.
- **Verification Green (`#00E676` - Tertiary / Success):** Scan locks, confirmed pick/pack verifications, and optimal signal strength acknowledgments.
- **Critical Red (`#FF3D00` - Destructive / Alert):** Beacon offline, misplaced pallet, expired route, battery critical.
- **Industrial Base (`#121518` - Dark Surface Canvas):** Low-reflectance graphite foundation. Elevated cards and control blocks scale upward through `#1B2026` to `#242B33` to delineate physical component boundaries without relying on soft atmospheric shadows.
- **Rule Lines & Crisp Dividers (`#333F4D`):** High-definition delineators ensuring touch zones remain distinct through smudged protective screens.

## Typography

The type system pairs the technical, mono-adjacent cadence of **Space Grotesk** with the neutral, hyper-legible mechanics of **Inter**. 

- **Space Grotesk** is reserved for headlines, operational numbers, telemetry tags, MAC addresses, parcel tracking IDs, and control labels. Its geometric, angular cut-outs preserve readability when viewing handheld terminals at an arm's length or odd angles.
- **Inter** handles narrative status feeds, instructions, and dense logistics metadata. Weights are deliberately kept at 400 (regular) and above; hairline weights are forbidden to maintain legibility through heavy screen protectors, scratched handheld digitizers, and direct warehouse lighting.
- All uppercase labels carry explicit positive letter tracking (`0.04em` to `0.08em`) to speed up perceptual recognition during rapid pick-and-sort passes.

## Layout & Spacing

The layout is built upon a **Fluid Industrial Grid** engineered for edge-to-edge situational awareness.

- **Mobile / Rugged Handhelds (< 600px):** Single-column layout with pinned bottom control pods. Primary actions sit strictly within the bottom 40% of the viewport (the "Thumb Sector"). Top margins are maintained for passive system indicators (beacon signal strength, PWA battery, shift status).
- **Tablet / Forklift Mounts (600px - 1024px):** 6-column fluid structure. Two-tier master-detail views: left pane hosts real-time parcel queue, right pane hosts beacon proximity radar and spatial rack coordinates.
- **Desktop / Dispatch (1024px+):** 12-column density grid allowing multi-zone cross-docking tracking with persistent side navigation.
- **Rhythm & Touch Buffers:** Minimum interactive touch target dimension is **56px × 56px**, surrounded by at least `space-sm` (`0.5rem`) physical dead-band buffers to prevent adjacent mis-taps while wearing industrial grip gloves.

## Elevation & Depth

To maximize battery efficiency and ensure clarity on outdoor/industrial panels, this system rejects ambient multi-layer blurred drop shadows. Hierarchy is established strictly through **Tonal Stepping** and **High-Definition Contrast Borders**:

1. **Floor 0 (Base Canvas):** `#121518` – The ambient warehouse application backdrop.
2. **Floor 1 (Structural Cards & Modules):** `#1B2026` bounded by a 1px solid stroke of `#2E3842`.
3. **Floor 2 (Interactive Rows, Modals & Floating Trays):** `#242B33` with 1.5px solid stroke `#3D4B59`.
4. **Active/Locked Focus:** Interactive elements drop surface fills into dark tones while driving perimeter borders into full-intensity functional glows: `0 0 0 2px #00E5FF`.
5. **Radar & Proximity Stacking:** Physical proximity to Bluetooth beacons is illustrated through concentric step-line rings rather than soft blurs, matching mechanical radar displays.

## Shapes

The design system employs **Soft Industrial Cornering** (`roundedness: 1`). 

- Standard components (buttons, text inputs, list items) use `4px` (`0.25rem`) corner rounding. 
- High-level containers, modals, and warehouse zone badges use `8px` (`0.5rem`).
- This subtle rounding softens harsh corners to prevent visual strain during 10-hour shifts, while strictly maintaining the perception of rigid, machined hardware modules. Pill buttons and hyper-round forms are prohibited, as they waste valuable screen real estate inside condensed data-entry cards.

## Components

### Buttons
- **Primary Action (Scan / Confirm / Log):** Height 56px minimum. Solid `#00E5FF` fill with stark `#0B1015` bold uppercase typography. Full width on mobile/PWA thumb docks. Micro-feedback on tap: shifts instantly to `#00B8D4` without delayed spring animations.
- **Secondary Action (Filter / Hold):** Height 56px. Ghost style with 1.5px `#3D4B59` border, `#1B2026` background, `#FFFFFF` text. Focus state illuminates border to `#00E5FF`.
- **Destructive Action (Reject / Beacon Lost):** Height 56px. `#2D1214` surface with a 1.5px `#FF3D00` border and `#FF5722` text.

### Chips & Beacon Status Badges
- Height 32px to 36px. Compact, monospaced-style identifier badges.
- **Structure:** Left-aligned 8px pulsing status dot + uppercase tracking code.
- **States:** 
  - Connected: `#00E676` dot on `#11271D` container with `#00E676` border.
  - Searching: `#FFB300` dot on `#29210B` container with `#FFB300` border.
  - Critical/Lost: `#FF3D00` dot on `#29100E` container with `#FF3D00` border.

### Parcel Lists & Telemetry Feeds
- Surface: `#1B2026`, separated by 1px `#2E3842` horizontal rules. No dividers smaller than 1px.
- Min item height: 72px to facilitate fast finger flicking and single-tap selection.
- Left edge features a 4px vertical status indicator bar color-coded to the package's immediate stage (Staged, Scanning, Dispatched, Flagged).

### Input Fields & Barcode Overrides
- Height: 56px.
- Surface: `#161B20`, border: 1.5px `#3D4B59`.
- Typography: `Space Grotesk` 18px text to ensure high legibility of alphanumeric tracking serials.
- Clear button: Enlarged 44px × 44px hit-box aligned to the right edge for instant single-tap buffer clearing.

### Package Cards
- Structured as modular diagnostic blocks. Divided into three distinct zones:
  1. **Header Bar:** Monospaced Parcel ID and RSSI (Signal Strength) decibel readout.
  2. **Body:** Bay/Rack/Shelf coordinates in bold, 22px Space Grotesk.
  3. **Footer:** Battery telemetry level, assigned handler, and primary verification trigger.

### Beacon Signal Ranging Radar (Custom Component)
- An interactive dynamic vector ring visualization occupying the center display during parcel recovery mode.
- Concentric, technical range rings scale outward from 1m to 30m, transitioning from `#00E5FF` (Immediate) to `#333F4D` (Out of Range), complete with real-time RSSI signal-strength dBm values.