import type { EncounterState, Faction, UnitState, Winner } from './types';

export function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function compareUnitIds(left: string, right: string): number {
  const leftPrefix = left[0];
  const rightPrefix = right[0];
  const leftNumber = Number(left.slice(1));
  const rightNumber = Number(right.slice(1));

  if (leftPrefix !== rightPrefix) {
    return leftPrefix === 'F' ? -1 : 1;
  }

  return leftNumber - rightNumber;
}

export function getUnitsByFaction(state: EncounterState, faction: Faction): UnitState[] {
  return Object.values(state.units)
    .filter((unit) => unit.faction === faction)
    .sort((left, right) => compareUnitIds(left.id, right.id));
}

export function isUnitDead(unit: UnitState): boolean {
  return unit.conditions.dead;
}

export function isUnitConscious(unit: UnitState): boolean {
  return unit.currentHp > 0 && !unit.conditions.dead && !unit.conditions.unconscious;
}

export function isUnitDying(unit: UnitState): boolean {
  return unit.currentHp === 0 && !unit.stable && !unit.conditions.dead;
}

export function isUnitStableAtZero(unit: UnitState): boolean {
  return unit.currentHp === 0 && unit.stable && !unit.conditions.dead;
}

export function getRemainingHp(units: UnitState[]): number {
  return units.reduce((total, unit) => total + unit.currentHp, 0);
}

export function getFinalWinner(state: EncounterState): Winner {
  const fighters = getUnitsByFaction(state, 'fighters');
  const goblins = getUnitsByFaction(state, 'goblins');
  const anyLivingFighter = fighters.some((unit) => !unit.conditions.dead);
  const anyLivingGoblin = goblins.some((unit) => !unit.conditions.dead);

  if (!anyLivingGoblin && anyLivingFighter) {
    return 'fighters';
  }

  if (!anyLivingFighter && anyLivingGoblin) {
    return 'goblins';
  }

  if (!anyLivingGoblin && !anyLivingFighter) {
    return 'mutual_annihilation';
  }

  return 'goblins';
}

export function describeWinner(winner: Winner | null): string {
  if (winner === 'fighters') {
    return 'Fighters win';
  }

  if (winner === 'goblins') {
    return 'Goblins win';
  }

  if (winner === 'mutual_annihilation') {
    return 'Mutual annihilation';
  }

  return 'Unresolved';
}
