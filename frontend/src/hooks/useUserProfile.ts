import type { UserMemoryProfile } from '../types/api';
import { readJson, writeJson } from '../utils/storage';

const PROFILE_KEY = 'webagents_user_profile';

export function loadProfile(_profileId?: string): UserMemoryProfile | null {
  return readJson<UserMemoryProfile | null>(PROFILE_KEY, null);
}

export function saveProfile(_profileId: string, profile: UserMemoryProfile): void {
  writeJson(PROFILE_KEY, profile);
}
