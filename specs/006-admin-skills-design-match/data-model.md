# Data Model: Admin Skills Design Match

## SkillSummary

Represents a saved skill shown in the Admin Skills list.

### Fields

- `name: string` - Stable skill identifier and display label.
- `description: string` - Short skill purpose text.

### Validation Rules

- Name must continue to follow the existing skill-name rules when created: lowercase letters, numbers, and hyphens; max 64 characters.
- Description must remain non-empty and max 256 characters for create/edit flows.
- Long names or descriptions must not break the Admin list layout; text should wrap or truncate consistently with Agent Builder list cards.

## SkillFormState

Represents the create/edit skill form state already managed by `SkillBuilder`.

### Fields

- `formName: string` - Editable for create mode, read-only for edit mode.
- `formDescription: string` - Editable description.
- `formContent: string` - Editable Markdown skill instructions.
- `editingName: string | null` - Selected skill name in edit mode.
- `formLoading: boolean` - Existing async save/load state.
- `aiLoading: boolean` - Existing AI content generation state.

### Validation Rules

- Create mode requires valid `formName`, non-empty `formDescription`, and non-empty `formContent`.
- Edit mode requires non-empty `formDescription` and `formContent`; name remains read-only.
- Content remains max 65,536 characters.

### State Transitions

- `list -> create`: User chooses new skill; form resets and opens create state.
- `list -> edit`: User chooses edit on a skill; form loads existing skill definition.
- `create/edit -> list`: User saves, cancels, or completes delete flow.
- `edit -> edit`: User regenerates content with AI; form content updates in place.

## AdminSkillsViewState

UI-only view state controlling Admin Skills presentation and feedback.

### Fields

- `loading: boolean` - Whether the skill list is loading.
- `view: 'list' | 'create' | 'edit'` - Existing mode value; implementation may keep this while rendering in one matched layout.
- `successMsg: string` - Success feedback.
- `errorMsg: string` - Error feedback.
- `deletingName: string | null` - Existing delete confirmation target.

### Presentation Rules

- List, create, and edit states must use Agent Builder-compatible panel styles.
- Feedback states must appear within the matched Admin layout and not as visually separate components.
- Empty and loading states must fit inside the left-list or form panel rhythm.
