import { ScheduleItem } from '../types';

export const SCHEDULE_ITEMS: ScheduleItem[] = [
  {
    name: 'Health watch',
    cadence: '*/5 * * * *',
    script: 'scripts/health-watch.sh',
    level: 'YELLOW',
    description: 'Inspects runtime endpoints, probes Model Router and repairs stale worker locks.',
  },
  {
    name: 'Repository watch',
    cadence: '*/30 * * * *',
    script: 'scripts/repo-watch.sh',
    level: 'GREEN',
    description: 'Monitors branch updates, pulls remote changes and validates CI contracts.',
  },
  {
    name: 'Daily revenue ops',
    cadence: '0 8 * * *',
    script: 'scripts/revenue-ops.sh',
    level: 'GREEN',
    description: 'Enriches lead records, updates opportunities pipeline and prepares mini-audit drafts.',
  },
  {
    name: 'Daily operations brief',
    cadence: '0 19 * * *',
    script: 'scripts/ops-brief.sh',
    level: 'GREEN',
    description: 'Aggregates 24-hour activity, evidence ledger proofs and task summary for OSA.',
  },
  {
    name: 'Weekly system audit',
    cadence: '0 18 * * 0',
    script: 'scripts/weekly-audit.sh',
    level: 'GREEN',
    description: 'Performs deep hash-chain validation, backup integrity testing and security scans.',
  },
  {
    name: 'Duty-cycle report',
    cadence: '0 5 * * *',
    script: 'scripts/hermes-report.sh',
    level: 'GREEN',
    description: 'Generates sanitized performance metrics and spend budget accounting.',
  },
];
