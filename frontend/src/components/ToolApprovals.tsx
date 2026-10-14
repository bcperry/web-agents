import { Check, ShieldQuestion, X } from 'lucide-react';
import type { ToolApprovalRequest } from '../types/api';

interface ToolApprovalsProps {
  requests: ToolApprovalRequest[];
  disabled: boolean;
  onRespond: (approved: boolean) => void;
}

export function ToolApprovals({ requests, disabled, onRespond }: ToolApprovalsProps) {
  if (requests.length === 0) return null;
  return (
    <section className="tool-approvals" aria-label="Tool approvals" aria-live="polite">
      <h3><ShieldQuestion size={18} aria-hidden="true" /> Approval Required</h3>
      <ul>
        {requests.map(request => (
          <li key={request.id}>
            <strong>{request.function_call.name}</strong>
            <pre>{typeof request.function_call.arguments === 'string'
              ? request.function_call.arguments
              : JSON.stringify(request.function_call.arguments ?? {}, null, 2)}</pre>
          </li>
        ))}
      </ul>
      <div className="tool-approval-actions">
        <button className="chat-input-send" type="button" onClick={() => onRespond(false)} disabled={disabled}>
          <X size={16} aria-hidden="true" /> Deny{requests.length > 1 ? ' All' : ''}
        </button>
        <button className="chat-input-send" type="button" onClick={() => onRespond(true)} disabled={disabled}>
          <Check size={16} aria-hidden="true" /> Approve{requests.length > 1 ? ' All' : ''}
        </button>
      </div>
    </section>
  );
}