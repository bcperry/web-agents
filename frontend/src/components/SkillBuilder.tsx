import { useState, useEffect, useCallback } from 'react';
import type { SkillSummary, SkillDefinition, SkillCreatePayload } from '../types/api';
import { fetchSkills, fetchSkill, createSkill, updateSkill, deleteSkill, generateSkillContent } from '../api/client';

type ViewMode = 'list' | 'create' | 'edit';

const SKILL_NAME_RE = /^[a-z0-9][a-z0-9-]*$/;

export function SkillBuilder() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<ViewMode>('list');

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
    } catch (err) {
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

  if (view === 'create') {
    return (
      <div className="skill-builder">
        <div className="skill-form-header">
          <button className="skill-btn-secondary" onClick={handleBack} type="button">
            ← BACK
          </button>
          <h3 className="skill-form-title">NEW SKILL</h3>
        </div>
        {errorMsg && <div className="skill-error">{errorMsg}</div>}
        {successMsg && <div className="skill-success">{successMsg}</div>}
        <form className="skill-form" onSubmit={handleCreate}>
          <div className="skill-form-field">
            <label className="agent-builder-label" htmlFor="skill-name">
              NAME <span className="skill-hint">(lowercase letters, numbers, hyphens)</span>
            </label>
            <input
              id="skill-name"
              className="agent-builder-input"
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="e.g. my-skill"
              maxLength={64}
              disabled={formLoading}
              required
            />
          </div>
          <div className="skill-form-field">
            <label className="agent-builder-label" htmlFor="skill-description">
              DESCRIPTION
            </label>
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
          </div>
          <div className="skill-form-field">
            <label className="agent-builder-label" htmlFor="skill-content">
              CONTENT (Markdown)
            </label>
            <div className="skill-ai-row">
              <button
                className="skill-btn-ai"
                type="button"
                onClick={handleGenerateWithAI}
                disabled={aiLoading || formLoading || !formDescription.trim()}
                title="Generate Markdown content from the description above"
              >
                {aiLoading ? 'GENERATING…' : '✨ GENERATE WITH AI'}
              </button>
              <span className="skill-ai-hint">Uses the description above as the prompt</span>
            </div>
            <textarea
              id="skill-content"
              className="skill-textarea"
              value={formContent}
              onChange={(e) => setFormContent(e.target.value)}
              placeholder={'# Skill Instructions\n\nWrite the skill instructions here in Markdown...'}
              maxLength={65536}
              disabled={formLoading}
              required
              rows={16}
            />
          </div>
          <div className="agent-builder-actions">
            <button
              className="agent-builder-save"
              type="submit"
              disabled={formLoading || !isCreateFormValid}
            >
              {formLoading ? 'CREATING...' : 'CREATE SKILL'}
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
      </div>
    );
  }

  if (view === 'edit') {
    return (
      <div className="skill-builder">
        <div className="skill-form-header">
          <button className="skill-btn-secondary" onClick={handleBack} type="button">
            ← BACK
          </button>
          <h3 className="skill-form-title">EDIT SKILL — {editingName}</h3>
        </div>
        {errorMsg && <div className="skill-error">{errorMsg}</div>}
        {successMsg && <div className="skill-success">{successMsg}</div>}
        {formLoading && !formContent ? (
          <div className="agent-builder-loading">Loading skill...</div>
        ) : (
          <form className="skill-form" onSubmit={handleUpdate}>
            <div className="skill-form-field">
              <label className="agent-builder-label" htmlFor="skill-name-ro">
                NAME <span className="skill-hint">(read-only)</span>
              </label>
              <input
                id="skill-name-ro"
                className="agent-builder-input"
                type="text"
                value={formName}
                readOnly
                disabled
              />
            </div>
            <div className="skill-form-field">
              <label className="agent-builder-label" htmlFor="skill-edit-description">
                DESCRIPTION
              </label>
              <input
                id="skill-edit-description"
                className="agent-builder-input"
                type="text"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder="Brief description"
                maxLength={256}
                disabled={formLoading}
                required
              />
            </div>
            <div className="skill-form-field">
              <label className="agent-builder-label" htmlFor="skill-edit-content">
                CONTENT (Markdown)
              </label>
              <div className="skill-ai-row">
                <button
                  className="skill-btn-ai"
                  type="button"
                  onClick={handleGenerateWithAI}
                  disabled={aiLoading || formLoading || !formDescription.trim()}
                  title="Regenerate Markdown content from the description above (replaces current content)"
                >
                  {aiLoading ? 'GENERATING…' : '✨ GENERATE WITH AI'}
                </button>
                <span className="skill-ai-hint">Replaces current content</span>
              </div>
              <textarea
                id="skill-edit-content"
                className="skill-textarea"
                value={formContent}
                onChange={(e) => setFormContent(e.target.value)}
                placeholder="# Skill Instructions..."
                maxLength={65536}
                disabled={formLoading}
                required
                rows={16}
              />
            </div>
            <div className="agent-builder-actions">
              <button
                className="agent-builder-save"
                type="submit"
                disabled={formLoading || !isEditFormValid}
              >
                {formLoading ? 'SAVING...' : 'SAVE CHANGES'}
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
    );
  }

  // List view
  return (
    <div className="skill-builder">
      <div className="skill-builder-header">
        <h3 className="skill-builder-title">SKILLS</h3>
        <button className="skill-btn-primary" onClick={handleOpenCreate} type="button">
          + NEW SKILL
        </button>
      </div>

      {errorMsg && <div className="skill-error">{errorMsg}</div>}
      {successMsg && <div className="skill-success">{successMsg}</div>}

      {loading ? (
        <div className="agent-builder-loading">Loading skills...</div>
      ) : skills.length === 0 ? (
        <div className="skill-empty">
          No skills defined yet. Click <strong>+ NEW SKILL</strong> to create one.
        </div>
      ) : (
        <div className="skill-list">
          {skills.map((skill) => (
            <div key={skill.name} className="skill-card">
              <div className="skill-card-info">
                <div className="skill-card-name">{skill.name}</div>
                <div className="skill-card-description">{skill.description}</div>
              </div>
              <div className="skill-card-actions">
                {deletingName === skill.name ? (
                  <div className="skill-delete-confirm">
                    <span>Delete "{skill.name}"?</span>
                    <button
                      className="skill-btn-danger"
                      type="button"
                      onClick={() => handleDeleteConfirm(skill.name)}
                    >
                      CONFIRM
                    </button>
                    <button
                      className="skill-btn-secondary"
                      type="button"
                      onClick={() => setDeletingName(null)}
                    >
                      CANCEL
                    </button>
                  </div>
                ) : (
                  <>
                    <button
                      className="skill-btn-secondary"
                      type="button"
                      onClick={() => handleOpenEdit(skill.name)}
                    >
                      EDIT
                    </button>
                    <button
                      className="skill-btn-danger"
                      type="button"
                      onClick={() => setDeletingName(skill.name)}
                    >
                      DELETE
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
