import type { DiceSpec } from './types';

const FNV_OFFSET = 2166136261;
const FNV_PRIME = 16777619;

export function normalizeSeed(seed: string): number {
  let hash = FNV_OFFSET;

  for (let index = 0; index < seed.length; index += 1) {
    hash ^= seed.charCodeAt(index);
    hash = Math.imul(hash, FNV_PRIME) >>> 0;
  }

  return hash === 0 ? 1 : hash;
}

export function nextRngState(state: number): number {
  return (Math.imul(state, 1664525) + 1013904223) >>> 0;
}

export function rollDie(state: number, sides: number): { value: number; state: number } {
  const nextState = nextRngState(state);
  const value = (nextState % sides) + 1;

  return { value, state: nextState };
}

export function rollDice(
  state: number,
  specs: DiceSpec[]
): { values: number[]; total: number; state: number } {
  const values: number[] = [];
  let total = 0;
  let workingState = state;

  for (const spec of specs) {
    for (let index = 0; index < spec.count; index += 1) {
      const roll = rollDie(workingState, spec.sides);
      workingState = roll.state;
      values.push(roll.value);
      total += roll.value;
    }
  }

  return {
    values,
    total,
    state: workingState
  };
}
