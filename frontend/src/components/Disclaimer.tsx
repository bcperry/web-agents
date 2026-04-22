import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';

const STORAGE_KEY = 'disclaimer_acknowledged';

function isAcknowledged(): boolean {
  return sessionStorage.getItem(STORAGE_KEY) === 'true';
}

export function Disclaimer({ children }: { children: React.ReactNode }) {
  const [acknowledged, setAcknowledged] = useState(isAcknowledged);
  const { classificationBanner } = useAuth();

  if (acknowledged) {
    return <>{children}</>;
  }

  const handleAcknowledge = () => {
    sessionStorage.setItem(STORAGE_KEY, 'true');
    setAcknowledged(true);
  };

  return (
    <div className="disclaimer-overlay">
      <div className="disclaimer-content">
        <h1>&#9888;&#65039; WARNING &#9888;&#65039;</h1>
        <h2>You are accessing a proprietary information system.</h2>
        <p>
          This information system, including all related equipment, networks, and network
          devices (specifically including Internet access), is provided only for authorized
          company use. Unauthorized or improper use of this system may result in disciplinary
          action, as well as civil and criminal penalties.
        </p>
        <p><strong>By using this information system, you understand and consent to the following:</strong></p>
        <ul>
          <li>
            You have no reasonable expectation of privacy regarding any communication or data
            transiting or stored on this information system. At any time, and for any lawful
            purpose, the company may monitor, intercept, search, and seize any communication
            or data transiting or stored on this information system.
          </li>
          <li>
            Any communication or data transiting or stored on this information system may be
            disclosed or used for any lawful company purpose.
          </li>
          <li>
            This AI system may produce inaccurate information. Always verify critical
            information through official channels.
          </li>
          <li>
            <strong>Do not enter sensitive information into this system.</strong>
          </li>
        </ul>
        <div className="classified-warning">
          {classificationBanner}
        </div>
        <button className="acknowledge-btn" onClick={handleAcknowledge} type="button">
          I UNDERSTAND AND AGREE
        </button>
      </div>
    </div>
  );
}
