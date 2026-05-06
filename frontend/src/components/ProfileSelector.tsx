import type { AgentProfile } from '../types/api';

interface Props {
  profiles: AgentProfile[];
  onSelect: (profileId: string) => void;
}

export function ProfileSelector({ profiles, onSelect }: Props) {
  return (
    <div className="profile-selector">
      <h2 className="profile-selector-title">SELECT YOUR AGENT</h2>
      <div className="profile-cards">
        {profiles.map((profile) => (
          <button
            key={profile.id}
            className="profile-card"
            onClick={() => onSelect(profile.id)}
            type="button"
          >
            <img
              className="profile-card-icon"
              src={profile.icon}
              alt={profile.name}
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none';
              }}
            />
            <div className="profile-card-name">{profile.name}</div>
            <div className="profile-card-desc">{profile.description}</div>
            {profile.isCustomized && <span className="profile-card-badge profile-card-badge--customized">CUSTOMIZED</span>}
            {profile.isCustom && <span className="profile-card-badge">CUSTOM</span>}
          </button>
        ))}
      </div>
    </div>
  );
}
