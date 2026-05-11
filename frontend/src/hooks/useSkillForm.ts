import { useState } from 'react';
import type { SkillCreatePayload } from '../types/api';

export type SkillBuilderViewMode = 'list' | 'create' | 'edit';

export const SKILL_NAME_RE = /^[a-z0-9][a-z0-9-]*$/;

export function useSkillForm() {
  const [view, setView] = useState<SkillBuilderViewMode>('list');
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formContent, setFormContent] = useState('');
  const [editingName, setEditingName] = useState<string | null>(null);
  const [formLoading, setFormLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [deletingName, setDeletingName] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);

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

  const createPayload = (): SkillCreatePayload => ({
    name: formName,
    description: formDescription,
    content: formContent,
  });

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

  return {
    aiLoading,
    clearFeedback,
    createPayload,
    deletingName,
    editingName,
    errorMsg,
    formContent,
    formDescription,
    formLoading,
    formName,
    isCreateFormValid,
    isEditFormValid,
    resetForm,
    setAiLoading,
    setDeletingName,
    setEditingName,
    setErrorMsg,
    setFormContent,
    setFormDescription,
    setFormLoading,
    setFormName,
    setSuccessMsg,
    setView,
    successMsg,
    view,
  };
}