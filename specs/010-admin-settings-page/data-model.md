# Data Model: Admin Settings Page

## Theme Preference

Represents the user's local UI color mode.

**Fields**:

- `mode`: enum, one of `light` or `dark`.
- `storageKey`: constant `webagents_theme` managed by the existing theme hook.
- `colorScheme`: derived value, currently equal to `mode`, applied to `document.documentElement.dataset.theme`.

**Validation Rules**:

- Only `light` and `dark` are accepted.
- Missing or invalid stored values fall back to `light`.
- Changes persist immediately through the existing `setMode` behavior.

**Relationships**:

- Rendered and modified in Admin Settings.
- Applied globally through `ThemeProvider`.

## Authenticated User Display

Represents identity information shown in the settings gear surface.

**Fields**:

- `email`: optional string from the authenticated user object.
- `canLogout`: boolean derived from the presence of an auth logout action.

**Validation Rules**:

- Email display must tolerate empty, missing, or very long values.
- Long email values must truncate or wrap without overflowing the menu or Admin settings layout.
- Logout action is shown only when a logout handler is available.

**Relationships**:

- Displayed in the chat header settings menu.
- May also be summarized in the Admin Settings section for account context.

## Admin Section

Represents top-level content areas in the Admin page.

**Fields**:

- `id`: enum, one of `settings`, `agents`, or `skills`.
- `label`: display label for the Admin tab.
- `content`: rendered React content for the selected section.

**Validation Rules**:

- Default active section is `settings`.
- `agents` renders existing `AgentBuilder` behavior.
- `skills` renders existing `SkillBuilder` behavior.
- Unknown section values are not exposed in UI state.

**State Transitions**:

- `settings` -> `agents` when the Agents tab is selected.
- `settings` -> `skills` when the Skills tab is selected.
- `agents` or `skills` -> `settings` when the Settings tab is selected.
- Any Admin section -> chat/profile selection when Back to Chat is selected.

## Settings Gear Menu

Represents the compact top-right settings surface in authenticated chat headers.

**Fields**:

- `isOpen`: boolean local component state.
- `userEmail`: optional string shown as account identity.
- `onOpenAdmin`: command callback.
- `onLogout`: optional command callback.

**Validation Rules**:

- Gear button must have an accessible name.
- Menu actions must be keyboard reachable.
- Selecting Admin must close or leave the menu safely as navigation occurs.
- Menu must not render outside the viewport at desktop, tablet, or mobile widths.