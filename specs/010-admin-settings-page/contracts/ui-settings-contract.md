# UI Contract: Header Settings Gear and Admin Settings

## Header Settings Gear

### Surface

- The authenticated chat header exposes one settings gear button in the top-right action area.
- The gear appears on both profile-selection and active-chat headers.
- The gear has an accessible name such as `Open settings`.

### Menu Content

- Shows signed-in user email when available.
- Shows an Admin action that navigates to the existing Admin page view.
- Shows Logout when a logout action is available.
- Does not show theme controls; theme lives in Admin Settings.

### Interaction

- Click or keyboard activation opens/closes the menu.
- Admin action calls the existing Admin navigation callback.
- Logout action calls the existing auth logout callback.
- Menu remains within viewport and handles long email strings without overflow.

## Admin Page Settings Section

### Navigation

- Admin page exposes tabs: Settings, Agents, Skills.
- Settings is the default active tab.
- Back to Chat retains existing browser history semantics.

### Theme Control

- Settings section exposes Light and Dark options.
- Selected option reflects `useTheme().mode`.
- Selecting an option calls `useTheme().setMode(mode)`.
- Theme updates globally immediately and persists through the existing localStorage key.

### Existing Sections

- Agents tab renders the existing `AgentBuilder` with current props.
- Skills tab renders the existing `SkillBuilder`.
- Existing save/delete/reset callbacks remain unchanged.

## Sidebar Contract

- Sidebar renders conversation navigation and New Chat controls.
- Sidebar no longer renders theme controls.
- Sidebar no longer renders Admin, user email, or Logout controls.