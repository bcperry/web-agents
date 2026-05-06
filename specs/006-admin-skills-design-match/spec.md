# Feature Specification: Admin Skills Design Match

**Feature Branch**: `006-admin-skills-design-match`  
**Created**: 2026-05-06  
**Status**: Draft  
**Input**: User description: "the design language difference between the agents and skills sections in the admin page is jarring. make the skills match the agents side."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Match Skills To Agent Builder Layout (Priority: P1)

As an admin user, I can switch between Agents and Skills without seeing a jarring design-language change, so Admin feels like one coherent management surface.

**Why this priority**: The request is specifically about visual consistency between the two Admin tabs. The MVP must make the Skills tab use the same structural language as the Agents side.

**Independent Test**: Open Admin, switch from Agents to Skills, and verify the Skills tab uses the same panel framing, section headers, spacing, monospace labels, form density, list card treatment, and action button style as Agent Builder.

**Acceptance Scenarios**:

1. **Given** the Admin page is open on Agents, **When** the user switches to Skills, **Then** the Skills management view uses the same left-list/right-form layout pattern as Agents.
2. **Given** saved skills exist, **When** the Skills tab renders, **Then** skill rows visually match custom-agent rows in border treatment, text hierarchy, spacing, and actions.
3. **Given** no skills exist or skills are loading, **When** the Skills tab renders, **Then** empty/loading states still fit the same Admin design language rather than appearing as a separate component family.

---

### User Story 2 - Keep Skill Editing Workflows Intact (Priority: P2)

As an admin user, I can create, edit, and delete skills exactly as before while benefiting from the updated visual design.

**Why this priority**: Visual alignment must not regress the functional Skill Builder workflow.

**Independent Test**: Create or edit a skill from the Skills tab after the redesign and verify the same fields, validation, save, cancel, and delete behaviors remain available.

**Acceptance Scenarios**:

1. **Given** the user opens an existing skill, **When** they choose edit, **Then** the same skill name, description, and content fields populate in the matched Admin form.
2. **Given** the user edits skill content, **When** they save, **Then** the existing skill save behavior works unchanged.
3. **Given** the user cancels an edit, **When** they return to the list, **Then** the view returns to the matched create-new-skill state without stale form data.

---

### User Story 3 - Verify Responsive Admin Consistency (Priority: P3)

As an admin user on smaller screens, I can manage skills without overflow, clipping, or awkward spacing that differs from the Agents tab.

**Why this priority**: Previous Admin layout work exposed responsive spacing issues; this redesign touches the same surface and must remain stable.

**Independent Test**: Capture desktop, tablet, and mobile screenshots of the Skills tab and compare against the Agents layout expectations for spacing, wrapping, and visible controls.

**Acceptance Scenarios**:

1. **Given** a desktop viewport, **When** the Skills tab renders, **Then** the list and form align in the same grid rhythm as Agents.
2. **Given** tablet or mobile viewport, **When** the Skills tab renders, **Then** the layout stacks or scrolls without horizontal overflow.

### Edge Cases

- No skills are present or the skills API returns an empty list.
- Skill names or descriptions are long enough to wrap or truncate.
- Skill content is large enough to require textarea scrolling.
- The skills API fails while tools/profile data in other Admin tabs still works.
- The user edits a skill and switches tabs or collapses/scrolls the layout.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Skills management MUST visually match the Agent Builder Admin layout language, including panel framing, section title styling, spacing, list-card treatment, form-card treatment, and action button style.
- **FR-002**: Skills management MUST present saved skills in a left-side list section comparable to Agent Builder's built-in/custom agent list sections.
- **FR-003**: Skills management MUST present create/edit skill fields in a right-side form section comparable to Agent Builder's create/edit agent form.
- **FR-004**: Existing skill create, edit, delete, load, validation, and save behaviors MUST continue to work unchanged.
- **FR-005**: Skills list actions MUST use clear text labels or the same icon/text treatment selected for Agent Builder actions.
- **FR-006**: The Skills view MUST handle loading, error, empty, and success states using Admin-consistent styling.
- **FR-007**: The redesigned Skills view MUST avoid horizontal overflow at desktop, tablet, and mobile viewports.
- **FR-008**: The implementation MUST complete Playwright screenshot verification per the constitution, using reusable screenshot scripting when capturing repeated Admin states.

### Key Entities *(include if feature involves data)*

- **SkillSummary**: Existing skill list item shown in Admin. Key attributes are name, description, and any identifier used to edit/delete the skill.
- **SkillFormState**: Existing create/edit form state for name, description, and skill content.
- **AdminSkillsViewState**: UI-only state for loading, error, selected skill, form mode, and success feedback.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can switch from Agents to Skills and identify both as part of the same Admin design system without mismatched card, button, or form styling.
- **SC-002**: Existing skill create/edit/delete workflows remain usable without additional steps compared to the current Skills tab.
- **SC-003**: Desktop, tablet, and mobile screenshots show no horizontal overflow, overlapping controls, clipped labels, or isolated floating panels in the Skills tab.
- **SC-004**: Frontend lint and production build pass after the redesign.
- **SC-005**: Screenshot verification artifacts are saved under `screenshots/` and reviewed before completion.
