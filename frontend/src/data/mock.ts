/**
 * mock.ts — pipeline shape helpers only.
 *
 * All mock lead/run generation and static fixture metadata has been removed.
 * This file now only exports the pipeline-stage key list and the emptyPipeline
 * factory used to initialise blank pipeline state in the frontend types.
 */

import type { PipelineStage } from "../types";

const STAGE_LABELS: Record<PipelineStage["key"], string> = {
  discovered: "Discovered",
  compliance: "Compliance",
  heuristic: "Heuristic",
  deterministic: "Deterministic",
  tier1: "Tier 1",
  tier2: "Tier 2",
  persisted: "Persisted",
};

export const STAGE_KEYS: PipelineStage["key"][] = [
  "discovered",
  "compliance",
  "heuristic",
  "deterministic",
  "tier1",
  "tier2",
  "persisted",
];

/** Returns a blank pipeline with every stage in "pending" state. */
export function emptyPipeline(): PipelineStage[] {
  return STAGE_KEYS.map((k) => ({
    key: k,
    label: STAGE_LABELS[k],
    state: "pending",
  }));
}
