import { useState, useEffect, useCallback } from 'react';
import type { SkillSummary, SkillDefinition, SkillCreatePayload } from '../types/api';
import { fetchSkills, fetchSkill, createSkill, updateSkill, deleteSkill, generateSkillContent } from '../api/client';

type ViewMode = 'list' | 'create' | 'edit';

const SKILL_NAME_RE = /^[a-z0-9][a-z0-9-]*$/;

export function SkillBuilder() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<ViewMode>('list');
  const [skillsCollapsed, setSkillsCollapsed] = useState(false);

  // Form state
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formContent, setFormContent] = useState('');
  const [editingName, setEditingName] = useState<string | null>(null);
  const [formLoading, setFormLoading] = useState(false);

  // Feedback
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Delete confirm
  const [deletingName, setDeletingName] = useState<string | null>(null);

  // AI generation
  const [aiLoading, setAiLoading] = useState(false);

  const loadSkills = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchSkills();
      setSkills(data as SkillSummary[]);
    } catch (err) {
      console.error('Failed to load skills:', err);
      setErrorMsg('Failed to load skills.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  const clearFeedback = () => {
    setSuccessMsg('');
    setErrorMsg('');
  };

  const resetForm = () => {
    setFormName('');
    setFormDescription('');
    setFormContent('');
    setEditingName(null);
  };

  const handleOpenCreate = () => {
    clearFeedback();
    resetForm();
    setView('create');
  };

  const handleOpenEdit = async (name: string) => {
    clearFeedback();
    setFormLoading(true);
    setView('edit');
    setEditingName(name);
    try {
      const skill: SkillDefinition = await fetchSkill(name);
      setFormName(skill.name);
      setFormDescription(skill.description);
      setFormContent(skill.content);
    } catch {
      setErrorMsg('Failed to load skill for editing.');
    } finally {
      setFormLoading(false);
    }
  };

  const handleBack = () => {
    clearFeedback();
    resetForm();
    setView('list');
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    clearFeedback();
    if (!SKILL_NAME_RE.test(formName) || formName.length > 64) {
      setErrorMsg('Name must match ^[a-z0-9][a-z0-9-]*$ and be at most 64 characters.');
      return;
    }
    if (!formDescription.trim() || formDescription.length > 256) {
      setErrorMsg('Description must be non-empty (max 256 characters).');
      return;
    }
    if (!formContent.trim() || formContent.length > 65536) {
      setErrorMsg('Content must be non-empty (max 65536 characters).');
      return;
    }
    setFormLoading(true);
    try {
      const payload: SkillCreatePayload = {
        name: formName,
        description: formDescription,
        content: formContent,
      };
      await createSkill(payload);
      setSuccessMsg(`Skill "${formName}" created successfully.`);
      resetForm();
      await loadSkills();
      setView('list');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to create skill.');
    } finally {
      setFormLoading(false);
    }
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    clearFeedback();
    if (!formDescription.trim() || formDescription.length > 256) {
      setErrorMsg('Description must be non-empty (max 256 characters).');
      return;
    }
    if (!formContent.trim() || formContent.length > 65536) {
      setErrorMsg('Content must be non-empty (max 65536 characters).');
      return;
    }
    if (!editingName) return;
    setFormLoading(true);
    try {
      await updateSkill(editingName, { description: formDescription, content: formContent });
      setSuccessMsg(`Skill "${editingName}" updated successfully.`);
      await loadSkills();
      setView('list');
      resetForm();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to update skill.');
    } finally {
      setFormLoading(false);
    }
  };

  const handleGenerateWithAI = async () => {
    clearFeedback();
    if (!formDescription.trim()) {
      setErrorMsg('Enter a description first so the AI knows what to generate.');
      return;
    }
    setAiLoading(true);
    try {
      const content = await generateSkillContent(formDescription, formName || undefined);
      setFormContent(content);
      setSuccessMsg('Generated skill content from description.');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to generate skill content.');
    } finally {
      setAiLoading(false);
    }
  };

  const handleDeleteConfirm = async (name: string) => {
    clearFeedback();
    try {
      await deleteSkill(name);
      setSuccessMsg(`Skill "${name}" deleted.`);
      setDeletingName(null);
      if (editingName === name) {
        resetForm();
        setView('list');
      }
      await loadSkills();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to delete skill.');
      setDeletingName(null);
    }
  };

  const isCreateFormValid =
    SKILL_NAME_RE.test(formName) &&
    formName.length <= 64 &&
    formDescription.trim().length > 0 &&
    formDescription.length <= 256 &&
    formContent.trim().length > 0 &&
    formContent.length <= 65536;

  const isEditFormValid =
    formDescription.trim().length > 0 &&
    formDescription.length <= 256 &&
    formContent.trim().length > 0 &&
    formContent.length <= 65536;

  const isEditing = view === 'edit';
  const formTitle = isEditing ? `EDIT SKILL${editingName ? ` - ${editingName}` : ''}` : 'CREATE NEW SKILL';
  const submitLabel = isEditing ? 'SAVE CHANGES' : 'CREATE SKILL';
  const loadingLabel = isEditing ? 'SAVING...' : 'CREATING...';

  return (
    <div className="agent-builder skill-builder">
      <div className="agent-builder-header">
        <h2 className="agent-builder-title">SKILL BUILDER</h2>
      </div>

      <div className="agent-builder-layout skill-builder-layout">
        <div className="agent-builder-lists">
          <div className={`agent-builder-saved ${skillsCollapsed ? 'collapsed' : ''}`}>
            <button
              className="agent-builder-section-toggle"
              type="button"
              aria-expanded={!skillsCollapsed}
              onClick={() => setSkillsCollapsed((collapsed) => !collapsed)}
            >
              <span className="agent-builder-section-title">SAVED SKILLS</span>
              <span className="agent-builder-section-toggle-icon" aria-hidden="true">
                {skillsCollapsed ? '+' : '-'}
              </span>
            </button>

            {!skillsCollapsed && (
              <>
                <div className="skill-list-actions">
                  <button className="skill-list-new" onClick={handleOpenCreate} type="button">
                    NEW SKILL
                  </button>
                </div>

                {loading ? (
                  <div className="agent-builder-loading">Loading skills...</div>
                ) : skills.length === 0 ? (
                  <div className="skill-empty">No skills defined yet.</div>
                ) : (
                  skills.map((skill) => (
                    <div
                      key={skill.name}
                      className={`agent-builder-saved-entry ${editingName === skill.name ? 'editing' : ''}`}
                    >
                      <div className="agent-builder-saved-info">
                        <div className="agent-builder-saved-name">{skill.name}</div>
                        <div className="agent-builder-saved-desc">{skill.description || 'No description'}</div>
                      </div>
                      <div className="agent-builder-saved-actions">
                        {deletingName === skill.name ? (
                          <div className="skill-delete-confirm">
                            <span>Delete "{skill.name}"?</span>
                            <button type="button" onClick={() => handleDeleteConfirm(skill.name)}>
                              CONFIRM
                            </button>
                            <button type="button" onClick={() => setDeletingName(null)}>
                              CANCEL
                            </button>
                          </div>
                        ) : (
                          <>
                            <button type="button" onClick={() => handleOpenEdit(skill.name)}>
                              EDIT
                            </button>
                            <button type="button" onClick={() => setDeletingName(skill.name)}>
                              DELETE
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </>
            )}
          </div>
        </div>

        <div className="agent-builder-form skill-builder-form-panel">
          <h3 className="agent-builder-section-title">{formTitle}</h3>
          {errorMsg && <div className="skill-error">{errorMsg}</div>}
          {successMsg && <div className="skill-success">{successMsg}</div>}

          {isEditing && formLoading && !formContent ? (
            <div className="agent-builder-loading">Loading skill...</div>
          ) : (
            <form className="skill-form" onSubmit={isEditing ? handleUpdate : handleCreate}>
              <label className="agent-builder-label" htmlFor={isEditing ? 'skill-name-ro' : 'skill-name'}>
                NAME {isEditing ? <span className="skill-hint">(read-only)</span> : <span className="skill-hint">(lowercase letters, numbers, hyphens)</span>}
                <input
                  id={isEditing ? 'skill-name-ro' : 'skill-name'}
                  className="agent-builder-input"
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. my-skill"
                  maxLength={64}
                  disabled={formLoading || isEditing}
                  readOnly={isEditing}
                  required
                />
              </label>

              <label className="agent-builder-label" htmlFor="skill-description">
                DESCRIPTION
                <input
                  id="skill-description"
                  className="agent-builder-input"
                  type="text"
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="Brief description of what this skill does"
                  maxLength={256}
                  disabled={formLoading}
                  required
                />
              </label>

              <label className="agent-builder-label" htmlFor="skill-content">
                CONTENT (Markdown)
                <div className="skill-ai-row">
                  <button
                    className="skill-btn-ai"
                    type="button"
                    onClick={handleGenerateWithAI}
                    disabled={aiLoading || formLoading || !formDescription.trim()}
                    title={isEditing ? 'Regenerate Markdown content from the description above' : 'Generate Markdown content from the description above'}
                  >
                    {aiLoading ? 'GENERATING...' : 'GENERATE WITH AI'}
                  </button>
                  <span className="agent-builder-tool-desc">
                    {isEditing ? 'Replaces current content' : 'Uses the description above as the prompt'}
                  </span>
                </div>
                <textarea
                  id="skill-content"
                  className="agent-builder-textarea skill-textarea"
                  value={formContent}
                  onChange={(e) => setFormContent(e.target.value)}
                  placeholder={isEditing ? '# Skill Instructions...' : '# Skill Instructions\n\nWrite the skill instructions here in Markdown...'}
                  maxLength={65536}
                  disabled={formLoading}
                  required
                  rows={16}
                />
              </label>

              <div className="agent-builder-actions">
                <button
                  className="agent-builder-save"
                  type="submit"
                  disabled={formLoading || (isEditing ? !isEditFormValid : !isCreateFormValid)}
                >
                  {formLoading ? loadingLabel : submitLabel}
                </button>
                <button
                  className="agent-builder-cancel"
                  type="button"
                  onClick={handleBack}
                  disabled={formLoading}
                >
                  CANCEL
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
