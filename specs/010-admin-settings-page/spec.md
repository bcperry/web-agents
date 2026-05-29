# Feature Specification: Admin Settings Page

**Feature Branch**: `010-admin-settings-page`  
**Created**: 2026-05-29  
**Status**: Draft  
**Input**: User description: "lets move the themeing under the admin panel, and put the admin button, and user info in a settings gear in the top right. and finally, lets create a solid settings page (which is now called admin page) where those settings live"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open Settings From Chat Header (Priority: P1)

As an authenticated user, I want the chat screen to expose a compact settings gear in the top-right header area so that admin access and account information are available without taking space in the conversation sidebar.

**Why this priority**: This is the primary navigation change. It establishes the new home for admin entry and user identity controls.

**Independent Test**: From both the profile selection screen and an active chat screen, verify that a settings gear appears in the top-right header area, opens a menu or equivalent compact control, shows the signed-in user's identity, and provides an Admin entry point.

**Acceptance Scenarios**:

1. **Given** an authenticated user on the chat screen, **When** they inspect the top-right header, **Then** they see a settings gear control alongside existing chat actions.
2. **Given** the settings gear is opened, **When** the menu is displayed, **Then** the user's email and an Admin action are visible and usable.
3. **Given** the user selects Admin from the settings gear, **When** navigation completes, **Then** the Admin page opens using the existing browser history behavior.

---

### User Story 2 - Manage Theme From Admin Settings (Priority: P1)

As a user, I want theme selection to live inside the Admin page's settings area so the sidebar stays focused on conversations.

**Why this priority**: The user explicitly requested moving theming under the admin panel, and this setting must remain easy to find and persist.

**Independent Test**: Open the Admin page, navigate to Settings, switch between Light and Dark themes, return to chat, and refresh the page to confirm the selected theme persists.

**Acceptance Scenarios**:

1. **Given** the user opens Admin, **When** they select the Settings tab, **Then** the page includes a theme control with Light and Dark options.
2. **Given** the user changes the theme in Admin Settings, **When** they return to chat, **Then** the new theme is applied across the app.
3. **Given** the user refreshes the browser after selecting a theme, **When** the app loads, **Then** the previously selected theme remains active.

---

### User Story 3 - Admin Page Becomes Settings Hub (Priority: P2)

As an authenticated user, I want the Admin page to feel like a solid settings page with clear sections for app settings, agent management, and skill management.

**Why this priority**: The feature reframes Admin as the location where app-level settings live while preserving existing agent and skill builder workflows.

**Independent Test**: Open Admin and verify the page title, tabs, and content make Settings, Agents, and Skills discoverable without breaking existing agent or skill editing flows.

**Acceptance Scenarios**:

1. **Given** the Admin page is open, **When** the page renders, **Then** Settings, Agents, and Skills are available as distinct sections.
2. **Given** the user switches between Admin sections, **When** Agents or Skills is selected, **Then** existing builders continue to render and function as before.
3. **Given** the user uses the Back to Chat action, **When** navigation completes, **Then** the user returns to the previous chat/profile-selection view.

---

### User Story 4 - Sidebar Focuses On Conversations (Priority: P3)

As a user, I want the conversation sidebar to contain conversation controls only, so navigation is cleaner on both desktop and mobile.

**Why this priority**: Removing theme, admin, and user information from the sidebar reduces clutter and complements the new header settings control.

**Independent Test**: Open the sidebar expanded and collapsed on desktop and mobile widths; verify conversation history and new chat controls remain while theme/admin/user controls are absent.

**Acceptance Scenarios**:

1. **Given** the sidebar is expanded, **When** it renders, **Then** it shows conversation history and new-chat controls without theme, Admin, email, or logout controls.
2. **Given** the sidebar is collapsed or viewed on mobile, **When** the user needs settings, **Then** the top-right settings gear remains the path to admin/user information.

### Edge Cases

- The user may have a very long email address; the gear menu and Admin Settings user section must truncate or wrap without layout overflow.
- The user may navigate directly back from Admin after opening it through the gear; history handling must return to chat/profile-selection rather than producing a blank view.
- The app may be unauthenticated or loading; settings controls must not expose Admin navigation until the authenticated UI is rendered.
- Existing theme values in localStorage may be invalid; the current `useTheme` fallback behavior must continue to default safely.
- Mobile headers have less horizontal space; the settings gear must not overlap title, status, token usage, or New Chat actions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST remove the theme selector from the conversation sidebar.
- **FR-002**: The system MUST remove the Admin button and visible user email from the conversation sidebar.
- **FR-003**: The system MUST provide a settings gear control in the top-right area of authenticated chat/profile-selection headers.
- **FR-004**: The settings gear control MUST expose the signed-in user's email when available.
- **FR-005**: The settings gear control MUST expose an Admin navigation action.
- **FR-006**: If logout is currently available in the authenticated UI, the settings gear control SHOULD continue to expose logout in the same compact settings surface.
- **FR-007**: The Admin page MUST include a Settings section/tab that contains theme selection.
- **FR-008**: The theme selection UI MUST use the existing `useTheme` state and localStorage persistence behavior.
- **FR-009**: The Admin page MUST continue to provide access to the existing Agents and Skills sections.
- **FR-010**: Existing agent and skill builder behavior MUST remain unchanged except for their placement within the expanded Admin page tab structure.
- **FR-011**: The Admin page MUST present itself as the settings/admin hub with clear page title and tab labels.
- **FR-012**: Settings gear and Admin settings controls MUST be keyboard accessible and must provide clear accessible names.

### Key Entities *(include if feature involves data)*

- **Theme Preference**: Existing persisted UI preference with `light` and `dark` modes, stored via the current theme hook/localStorage key.
- **Authenticated User Display**: User identity value shown in the settings surface, currently sourced from authentication user email.
- **Admin Section**: UI section within the Admin page; includes Settings, Agents, and Skills.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can reach Admin from the chat screen with no more than two interactions: open settings gear, select Admin.
- **SC-002**: Users can change theme from Admin Settings and see the app-wide theme update immediately without page reload.
- **SC-003**: After a browser refresh, the previously selected theme remains active in at least 95% of manual verification attempts across supported browsers.
- **SC-004**: Sidebar visual clutter is reduced by removing the Advanced and Theme sections while preserving conversation history and new-chat functionality.
- **SC-005**: Frontend type-check/build completes successfully, and visual verification screenshots show no overlap or clipping at desktop, tablet, and mobile viewports for affected screens.