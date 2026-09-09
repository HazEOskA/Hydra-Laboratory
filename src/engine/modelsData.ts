import { ModelSpec, ProviderHealth } from '../types';

export const TASK_CLASSES = [
  'FAST_CLASSIFICATION',
  'CODE_GENERATION',
  'CODE_REVIEW',
  'DEEP_REASONING',
  'RESEARCH',
  'CONTENT',
  'VISION',
  'LONG_CONTEXT',
  'LOCAL_PRIVATE',
  'FALLBACK',
] as const;

export const MODELS_CATALOG: Record<string, ModelSpec> = {
  'router-default': {
    provider: 'nvidia-router',
    context_window: 128000,
    local: false,
    capabilities: ['text', 'reasoning', 'code', 'tools', 'long_context'],
    notes: 'Default routed pool selected during onboarding (routed).',
  },
  'router-fast': {
    provider: 'nvidia-router',
    context_window: 32000,
    local: false,
    capabilities: ['text', 'classification'],
    notes: 'Low-latency class for triage and classification.',
  },
  'router-reasoning': {
    provider: 'nvidia-router',
    context_window: 200000,
    local: false,
    capabilities: ['text', 'reasoning', 'code', 'long_context'],
    notes: 'High capacity reasoning model for architecture reviews and planning.',
  },
  'router-vision': {
    provider: 'nvidia-router',
    context_window: 64000,
    local: false,
    capabilities: ['text', 'vision'],
    notes: 'Vision model pool for UI screenshots and diagrams.',
  },
  'nvidia/nemotron-3-super-120b-a12b': {
    provider: 'nvidia-prod',
    context_window: 0,
    local: false,
    capabilities: ['text', 'reasoning', 'code', 'tools', 'long_context'],
    notes: 'Live model observed on hydra-hermes-runtime-01. Capabilities inferred from model family.',
  },
  'local-fallback': {
    provider: 'local',
    context_window: 16000,
    local: true,
    capabilities: ['text', 'classification'],
    notes: 'On-host local fallback model with narrow capability set for privacy.',
  },
};

export const ROUTES_CONFIG: Record<string, { preferred: string; fallback: string[]; local?: string }> = {
  FAST_CLASSIFICATION: {
    preferred: 'router-fast',
    fallback: ['router-default', 'nvidia/nemotron-3-super-120b-a12b'],
    local: 'local-fallback',
  },
  CODE_GENERATION: {
    preferred: 'router-default',
    fallback: ['router-reasoning', 'nvidia/nemotron-3-super-120b-a12b'],
  },
  CODE_REVIEW: {
    preferred: 'router-reasoning',
    fallback: ['router-default', 'nvidia/nemotron-3-super-120b-a12b'],
  },
  DEEP_REASONING: {
    preferred: 'router-reasoning',
    fallback: ['router-default', 'nvidia/nemotron-3-super-120b-a12b'],
  },
  RESEARCH: {
    preferred: 'router-default',
    fallback: ['router-reasoning', 'nvidia/nemotron-3-super-120b-a12b'],
  },
  CONTENT: {
    preferred: 'router-default',
    fallback: ['router-fast', 'nvidia/nemotron-3-super-120b-a12b'],
  },
  VISION: {
    preferred: 'router-vision',
    fallback: [],
  },
  LONG_CONTEXT: {
    preferred: 'router-reasoning',
    fallback: ['router-default', 'nvidia/nemotron-3-super-120b-a12b'],
  },
  LOCAL_PRIVATE: {
    preferred: 'local-fallback',
    fallback: [],
    local: 'local-fallback',
  },
  FALLBACK: {
    preferred: 'router-default',
    fallback: ['router-fast', 'nvidia/nemotron-3-super-120b-a12b'],
    local: 'local-fallback',
  },
};

export const INITIAL_HEALTH_TABLE: Record<string, ProviderHealth> = {
  'router-default': {
    provider: 'nvidia-router',
    model: 'router-default',
    status: 'HEALTHY',
    last_check: new Date().toISOString(),
    latency_ms: 320,
    recent_failures: 0,
    supported_capabilities: ['text', 'reasoning', 'code', 'tools', 'long_context'],
  },
  'router-fast': {
    provider: 'nvidia-router',
    model: 'router-fast',
    status: 'HEALTHY',
    last_check: new Date().toISOString(),
    latency_ms: 95,
    recent_failures: 0,
    supported_capabilities: ['text', 'classification'],
  },
  'router-reasoning': {
    provider: 'nvidia-router',
    model: 'router-reasoning',
    status: 'HEALTHY',
    last_check: new Date().toISOString(),
    latency_ms: 840,
    recent_failures: 0,
    supported_capabilities: ['text', 'reasoning', 'code', 'long_context'],
  },
  'router-vision': {
    provider: 'nvidia-router',
    model: 'router-vision',
    status: 'HEALTHY',
    last_check: new Date().toISOString(),
    latency_ms: 510,
    recent_failures: 0,
    supported_capabilities: ['text', 'vision'],
  },
  'nvidia/nemotron-3-super-120b-a12b': {
    provider: 'nvidia-prod',
    model: 'nvidia/nemotron-3-super-120b-a12b',
    status: 'HEALTHY',
    last_check: new Date().toISOString(),
    latency_ms: 415,
    recent_failures: 0,
    supported_capabilities: ['text', 'reasoning', 'code', 'tools', 'long_context'],
  },
  'local-fallback': {
    provider: 'local',
    model: 'local-fallback',
    status: 'HEALTHY',
    last_check: new Date().toISOString(),
    latency_ms: 18,
    recent_failures: 0,
    supported_capabilities: ['text', 'classification'],
  },
};
