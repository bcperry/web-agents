# Research: Admin Settings Page

## Decision: Keep this as a frontend-only UI/navigation change

**Rationale**: The requested behavior moves existing controls: theme selection from `Sidebar` to `AdminPage`, and Admin/user identity from the sidebar into the chat header settings gear. All required state already exists in React (`useTheme`, `useAuth`, current `App` view navigation), so no backend endpoint, database change, or API contract change is needed.

**Alternatives considered**: Adding a backend settings endpoint was rejected because theme preference is already a local UI preference and user identity already comes from auth state.

## Decision: Reuse `useTheme` and the existing localStorage key

**Rationale**: `useTheme` already validates `light`/`dark`, persists to `webagents_theme`, and applies `data-theme` to the document root. Moving the control should not change preference semantics or migration needs.

**Alternatives considered**: Creating a new settings store was rejected because it would duplicate state and risk divergence with existing theme behavior.

## Decision: Add a reusable settings gear/menu component for authenticated headers

**Rationale**: `ChatPage` renders separate headers for the profile selection and active chat states. A small shared component keeps gear behavior, accessible labels, long-email handling, Admin navigation, and logout placement consistent across both headers.

**Alternatives considered**: Duplicating menu JSX in both header branches was rejected because it would make keyboard/menu behavior and future settings additions harder to maintain.

## Decision: Admin page gains a first-class `Settings` tab before `Agents` and `Skills`

**Rationale**: The current Admin page already uses tabs for top-level sections. Adding `Settings` as the default tab preserves the page model and makes theme/account settings discoverable without disrupting existing AgentBuilder and SkillBuilder flows.

**Alternatives considered**: Creating a separate settings page/view was rejected because the user's request explicitly reframes the Admin page as the settings location, and a new view would add unnecessary navigation state.

## Decision: Remove sidebar theme and advanced sections from `Sidebar`

**Rationale**: The sidebar should return to conversation-oriented controls. Removing settings/user/admin props from `Sidebar` clarifies ownership: chat headers own settings entry, Admin owns settings content, sidebar owns conversation list/new chat.

**Alternatives considered**: Keeping redundant sidebar controls was rejected because it conflicts with the stated goal and increases visual clutter, especially on mobile.

## Decision: Visual verification is required for desktop, tablet, and mobile affected screens

**Rationale**: The constitution requires screenshot-based verification for UI/layout/theming changes. This feature touches header layout, sidebar layout, Admin tabs, and theme controls, so screenshots must include profile selection, active chat, Admin Settings, and responsive widths.

**Alternatives considered**: Type-check-only validation was rejected because DOM/type checks cannot catch header overlap, clipped menus, or poor responsive layout.