import { ModelCapability, ModelSpec, ProviderHealth, RoutingDecision } from '../types';
import { INITIAL_HEALTH_TABLE, MODELS_CATALOG, ROUTES_CONFIG, TASK_CLASSES } from './modelsData';

export class ModelRouterEngine {
  private catalog: Record<string, ModelSpec>;
  private healthTable: Record<string, ProviderHealth>;

  constructor(
    customCatalog?: Record<string, ModelSpec>,
    customHealth?: Record<string, ProviderHealth>
  ) {
    this.catalog = customCatalog || { ...MODELS_CATALOG };
    this.healthTable = customHealth || { ...INITIAL_HEALTH_TABLE };
  }

  public getModels(): Record<string, ModelSpec> {
    return { ...this.catalog };
  }

  public getHealthTable(): Record<string, ProviderHealth> {
    return { ...this.healthTable };
  }

  public setProviderHealth(
    model: string,
    status: 'HEALTHY' | 'DEGRADED' | 'DOWN',
    latency = 120
  ): void {
    if (this.healthTable[model]) {
      this.healthTable[model] = {
        ...this.healthTable[model],
        status,
        latency_ms: latency,
        last_check: new Date().toISOString(),
      };
    }
  }

  public chainFor(taskClass: string): string[] {
    const route = ROUTES_CONFIG[taskClass];
    if (!route) {
      throw new Error(`Unknown task class: ${taskClass}. Available: ${TASK_CLASSES.join(', ')}`);
    }
    const chain = [route.preferred, ...(route.fallback || [])];
    if (route.local) {
      chain.push(route.local);
    }
    return chain.filter(Boolean);
  }

  public select(
    taskClass: string,
    opts: {
      requiredCapabilities?: ModelCapability[];
      contextTokens?: number;
      privateOnly?: boolean;
      exclude?: string[];
    } = {}
  ): RoutingDecision {
    const chain = this.chainFor(taskClass);
    const required = new Set(opts.requiredCapabilities || []);
    const excluded = new Set(opts.exclude || []);
    const considered: string[] = [];
    const rejected: Record<string, string> = {};

    for (const model of chain) {
      considered.push(model);
      const spec = this.catalog[model];
      if (!spec) {
        rejected[model] = 'Not in the model catalog';
        continue;
      }

      if (excluded.has(model)) {
        rejected[model] = 'Excluded after a previous failure on this task';
        continue;
      }

      if (opts.privateOnly && !spec.local) {
        rejected[model] = 'Task requires a strictly local/private model';
        continue;
      }

      // Check capabilities
      const modelCaps = new Set(spec.capabilities);
      const missing = Array.from(required).filter((cap) => !modelCaps.has(cap));
      if (missing.length > 0) {
        rejected[model] = `Missing capabilities: ${missing.sort().join(', ')}`;
        continue;
      }

      // Check context window
      if (opts.contextTokens && spec.context_window && opts.contextTokens > spec.context_window) {
        rejected[model] = `Context ${opts.contextTokens} exceeds max window ${spec.context_window}`;
        continue;
      }

      // Check provider health
      const health = this.healthTable[model];
      const status = health ? health.status : 'DOWN';
      if (status === 'DOWN') {
        rejected[model] = 'Provider health is currently DOWN';
        continue;
      }

      return {
        task_class: taskClass,
        selected: model,
        provider: spec.provider,
        status: status === 'DEGRADED' ? 'DEGRADED' : 'ROUTED',
        reason:
          `Selected ${model} for ${taskClass}` +
          (status === 'DEGRADED' ? '; Provider is DEGRADED but usable' : ''),
        considered,
        rejected,
      };
    }

    return {
      task_class: taskClass,
      selected: null,
      provider: null,
      status: 'BLOCKED',
      reason: `No model in the ${taskClass} chain satisfies all requirements; Task blocked rather than routed to an unsuitable model`,
      considered,
      rejected,
    };
  }
}
