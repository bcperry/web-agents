# Research: Admin Skills Design Match

## Decision: Reuse Agent Builder layout primitives for Skills

**Rationale**: The jarring difference comes from Skills using its own centered layout and `skill-*` cards/buttons while Agents uses dense Admin panels with left-list/right-form structure. Reusing the Agent Builder layout primitives makes Admin feel coherent with the smallest implementation surface.

**Alternatives considered**:

- Create a new shared Admin design system first: rejected for this feature because it adds abstraction before proving the exact shared surface needed.
- Only adjust colors on existing Skills cards: rejected because the mismatch is structural, not just color-level.
- Move Skills into AgentBuilder: rejected because the workflows and API calls are separate; visual reuse does not require component merger.

## Decision: Keep existing SkillBuilder state and API behavior

**Rationale**: The request is visual consistency. Skill create, edit, delete, AI generation, validation, and API calls already exist and should remain behaviorally stable. The implementation should reshape JSX/classes around existing handlers rather than rewriting the workflow.

**Alternatives considered**:

- Refactor skill CRUD into a new hook: deferred because it is not needed to satisfy the design request.
- Add backend changes for richer skill metadata: rejected because existing `SkillSummary` and `SkillDefinition` are sufficient for the UI.

## Decision: Use a persistent left skill list plus right form

**Rationale**: Agents now presents management as a left rail of list panels and a right create/edit form. Skills should mirror that mental model: saved skills on the left, create/edit skill form on the right. This also prevents the create/edit view from feeling like a separate page.

**Alternatives considered**:

- Preserve separate list/create/edit pages with matched colors: rejected because tab switching would still feel abrupt.
- Use a modal for skill editing: rejected because Agent Builder uses inline forms and the request is to match that side.

## Decision: Extend reusable Playwright screenshot tooling for Skills

**Rationale**: The constitution now prefers reusable screenshot scripts for repeated Admin flows. This feature requires desktop/tablet/mobile screenshots of Skills states, so extending or mirroring the existing Admin screenshot script avoids large one-off terminal commands and makes future visual verification repeatable.

**Alternatives considered**:

- Inline Playwright heredocs: rejected because recent workflow showed they are noisy and expensive to repeat.
- Manual browser screenshots only: rejected by the constitution's automated visual verification requirement.
