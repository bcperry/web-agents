import type { UserMemoryProfile } from '../types/api';

const PROFILE_KEY = 'webagents_user_profile';

export function loadProfile(_profileId?: string): UserMemoryProfile | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as UserMemoryProfile;
  } catch {
    return null;
  }
}

export function saveProfile(_profileId: string, profile: UserMemoryProfile): void {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}
