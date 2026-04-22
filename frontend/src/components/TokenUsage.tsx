import type { UsageDetails } from '../types/api';

interface Props {
  usage: UsageDetails;
}

export function TokenUsage({ usage }: Props) {
  if (usage.total_token_count === 0) return null;

  return (
    <div className="token-usage">
      <span className="token-usage-detail">IN: {usage.input_token_count.toLocaleString()}</span>
      <span className="token-usage-detail"> | OUT: {usage.output_token_count.toLocaleString()}</span>
      <span className="token-usage-detail"> | TOTAL: {usage.total_token_count.toLocaleString()}</span>
    </div>
  );
}
