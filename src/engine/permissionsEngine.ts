import { Decision, PermissionLevel, ToolSpec } from '../types';
import { computePayloadHash } from './crypto';
import { RED_PATTERNS, TOOLS_REGISTRY } from './toolsData';

const ORDER: Record<PermissionLevel, number> = {
  GREEN: 0,
  YELLOW: 1,
  RED: 2,
};

export class PermissionClassifier {
  private tools: Record<string, ToolSpec>;
  private redPatterns = RED_PATTERNS;

  constructor(customTools?: Record<string, ToolSpec>) {
    this.tools = customTools || TOOLS_REGISTRY;
  }

  public knownTools(): string[] {
    return Object.keys(this.tools).sort();
  }

  public enabledTools(): string[] {
    return Object.keys(this.tools)
      .filter((k) => this.tools[k].enabled)
      .sort();
  }

  public toolSpec(tool: string): ToolSpec {
    const spec = this.tools[tool];
    if (!spec) {
      throw new Error(`Tool '${tool}' is not in the registry. Known: ${this.knownTools().join(', ')}`);
    }
    return spec;
  }

  private defaultLevel(tool: string, spec: ToolSpec, action: string): { level: PermissionLevel; rule: string } {
    if (spec.actions && action in spec.actions) {
      return { level: spec.actions[action], rule: `tools.${tool}.actions.${action}` };
    }

    for (const key of Object.keys(spec) as Array<keyof ToolSpec>) {
      if (key.endsWith('_permission')) {
        const verb = key.slice(0, -'_permission'.length);
        if (verb && (action === verb || action.startsWith(`${verb}_`) || action.endsWith(`_${verb}`))) {
          return { level: spec[key] as PermissionLevel, rule: `tools.${tool}.${key}` };
        }
      }
    }

    if (spec.permission_default) {
      return { level: spec.permission_default, rule: `tools.${tool}.permission_default` };
    }

    return { level: 'RED', rule: `tools.${tool}.unclassified` };
  }

  private patternEscalation(
    tool: string,
    action: string,
    payload: Record<string, any>
  ): { level: PermissionLevel; rule: string } | null {
    const haystack = `${tool} ${action} ${JSON.stringify(payload)}`.toLowerCase();
    for (const rule of this.redPatterns) {
      if (!rule.pattern) continue;
      if (rule.tools && !rule.tools.includes(tool)) continue;
      try {
        const regex = new RegExp(rule.pattern, 'i');
        if (regex.test(haystack)) {
          return { level: rule.permission, rule: rule.id };
        }
      } catch {
        // Fallback for invalid regex pattern
      }
    }
    return null;
  }

  public classify(
    tool: string,
    action: string,
    payload: Record<string, any> = {},
    rollbackAvailable = false
  ): Decision {
    const spec = this.toolSpec(tool);
    if (!spec.enabled) {
      throw new Error(`Tool '${tool}' is disabled in the registry`);
    }

    let { level, rule } = this.defaultLevel(tool, spec, action);
    let reason = `Registry rule ${rule}`;

    const escalation = this.patternEscalation(tool, action, payload);
    if (escalation) {
      if (ORDER[escalation.level] > ORDER[level]) {
        level = escalation.level;
        rule = escalation.rule;
        reason = `SOUL.md RED pattern ${escalation.rule}`;
      } else if (escalation.level === 'RED') {
        rule = escalation.rule;
        reason = `SOUL.md RED pattern ${escalation.rule}`;
      }
    }

    if (level === 'YELLOW' && !rollbackAvailable) {
      reason += '; YELLOW requires a rollback path';
    }

    const idempotencyKey = computePayloadHash({ tool, action, payload }).slice(0, 32);

    let dispatchPlan: Decision['dispatch_plan'] = 'DISPATCH';
    if (level === 'YELLOW') {
      dispatchPlan = 'CHECKPOINT_AUDIT_DISPATCH';
    } else if (level === 'RED') {
      dispatchPlan = 'REQUEST_APPROVAL_BLOCK_TASK';
    }

    return {
      tool,
      action,
      permission: level,
      reason,
      requires_approval: level === 'RED',
      rollback_available: rollbackAvailable,
      idempotency_key: idempotencyKey,
      matched_rule: rule,
      audit_required: level === 'YELLOW' || level === 'RED',
      evidence_refs: [],
      dispatch_plan: dispatchPlan,
    };
  }
}
