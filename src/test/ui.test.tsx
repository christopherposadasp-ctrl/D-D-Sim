import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  BatchSummary,
  CombatEvent,
  EnemyCatalogResponse,
  EncounterConfig,
  EncounterState,
  GridPosition,
  PlayerCatalogResponse,
  ReplayFrame,
  RunEncounterResult,
  UnitState,
} from '../shared/sim/types';
import { App } from '../ui/App';

const TEST_ENEMY_CATALOG: EnemyCatalogResponse = {
  "defaultEnemyPresetId": "goblin_screen",
  "enemyVariants": [
    {
      "id": "animated_armor",
      "displayName": "Animated Armor",
      "maxHp": 33,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "awakened_shrub",
      "displayName": "Awakened Shrub",
      "maxHp": 10,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "awakened_tree",
      "displayName": "Awakened Tree",
      "maxHp": 59,
      "footprint": {
        "width": 3,
        "height": 3
      }
    },
    {
      "id": "axe_beak",
      "displayName": "Axe Beak",
      "maxHp": 19,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "bandit_archer",
      "displayName": "Bandit Archer",
      "maxHp": 11,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "bandit_captain",
      "displayName": "Bandit Captain",
      "maxHp": 52,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "bandit_melee",
      "displayName": "Bandit Melee",
      "maxHp": 11,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "berserker",
      "displayName": "Berserker",
      "maxHp": 67,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "black_bear",
      "displayName": "Black Bear",
      "maxHp": 19,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "brown_bear",
      "displayName": "Brown Bear",
      "maxHp": 22,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "bugbear_warrior",
      "displayName": "Bugbear Warrior",
      "maxHp": 33,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "camel",
      "displayName": "Camel",
      "maxHp": 17,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "commoner",
      "displayName": "Commoner",
      "maxHp": 4,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "crocodile",
      "displayName": "Crocodile",
      "maxHp": 13,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "cultist",
      "displayName": "Cultist",
      "maxHp": 9,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "dire_wolf",
      "displayName": "Dire Wolf",
      "maxHp": 22,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "draft_horse",
      "displayName": "Draft Horse",
      "maxHp": 15,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "giant_badger",
      "displayName": "Giant Badger",
      "maxHp": 15,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "giant_crab",
      "displayName": "Giant Crab",
      "maxHp": 13,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "giant_fire_beetle",
      "displayName": "Giant Fire Beetle",
      "maxHp": 4,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "giant_hyena",
      "displayName": "Giant Hyena",
      "maxHp": 45,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "giant_lizard",
      "displayName": "Giant Lizard",
      "maxHp": 19,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "giant_rat",
      "displayName": "Giant Rat",
      "maxHp": 7,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "giant_toad",
      "displayName": "Giant Toad",
      "maxHp": 39,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "giant_weasel",
      "displayName": "Giant Weasel",
      "maxHp": 9,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "gnoll_warrior",
      "displayName": "Gnoll Warrior",
      "maxHp": 27,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "goblin_archer",
      "displayName": "Goblin Archer",
      "maxHp": 10,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "goblin_boss",
      "displayName": "Goblin Boss",
      "maxHp": 21,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "goblin_minion",
      "displayName": "Goblin Minion",
      "maxHp": 7,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "goblin_raider",
      "displayName": "Goblin Raider",
      "maxHp": 10,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "guard",
      "displayName": "Guard",
      "maxHp": 11,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "guard_captain",
      "displayName": "Guard Captain",
      "maxHp": 75,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "hobgoblin_archer",
      "displayName": "Hobgoblin Archer",
      "maxHp": 11,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "hobgoblin_warrior",
      "displayName": "Hobgoblin Warrior",
      "maxHp": 11,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "hyena",
      "displayName": "Hyena",
      "maxHp": 5,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "jackal",
      "displayName": "Jackal",
      "maxHp": 3,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "lemure",
      "displayName": "Lemure",
      "maxHp": 9,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "mastiff",
      "displayName": "Mastiff",
      "maxHp": 5,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "mule",
      "displayName": "Mule",
      "maxHp": 11,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "noble",
      "displayName": "Noble",
      "maxHp": 9,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "ogre",
      "displayName": "Ogre",
      "maxHp": 68,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "orc_warrior",
      "displayName": "Orc Warrior",
      "maxHp": 15,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "polar_bear",
      "displayName": "Polar Bear",
      "maxHp": 42,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "pony",
      "displayName": "Pony",
      "maxHp": 11,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "riding_horse",
      "displayName": "Riding Horse",
      "maxHp": 13,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "scout",
      "displayName": "Scout",
      "maxHp": 16,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "skeleton",
      "displayName": "Skeleton",
      "maxHp": 13,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "tiger",
      "displayName": "Tiger",
      "maxHp": 30,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "tough",
      "displayName": "Tough",
      "maxHp": 32,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "violet_fungus",
      "displayName": "Violet Fungus",
      "maxHp": 18,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "warrior_infantry",
      "displayName": "Warrior Infantry",
      "maxHp": 9,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "wolf",
      "displayName": "Wolf",
      "maxHp": 11,
      "footprint": {
        "width": 1,
        "height": 1
      }
    },
    {
      "id": "worg",
      "displayName": "Worg",
      "maxHp": 26,
      "footprint": {
        "width": 2,
        "height": 2
      }
    },
    {
      "id": "zombie",
      "displayName": "Zombie",
      "maxHp": 15,
      "footprint": {
        "width": 1,
        "height": 1
      }
    }
  ],
  "enemyPresets": [
    {
      "id": "goblin_screen",
      "displayName": "Goblin Screen",
      "description": "Three raiders screening three archers.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "goblin_raider",
          "position": {
            "x": 14,
            "y": 6
          }
        },
        {
          "unitId": "E2",
          "variantId": "goblin_raider",
          "position": {
            "x": 14,
            "y": 8
          }
        },
        {
          "unitId": "E3",
          "variantId": "goblin_raider",
          "position": {
            "x": 14,
            "y": 10
          }
        },
        {
          "unitId": "E4",
          "variantId": "goblin_archer",
          "position": {
            "x": 15,
            "y": 5
          }
        },
        {
          "unitId": "E5",
          "variantId": "goblin_archer",
          "position": {
            "x": 15,
            "y": 8
          }
        },
        {
          "unitId": "E6",
          "variantId": "goblin_archer",
          "position": {
            "x": 15,
            "y": 11
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    },
    {
      "id": "bandit_ambush",
      "displayName": "Bandit Ambush",
      "description": "Two melee bandits, two archers, and a scout.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "bandit_melee",
          "position": {
            "x": 14,
            "y": 7
          }
        },
        {
          "unitId": "E2",
          "variantId": "bandit_melee",
          "position": {
            "x": 14,
            "y": 9
          }
        },
        {
          "unitId": "E3",
          "variantId": "bandit_archer",
          "position": {
            "x": 15,
            "y": 5
          }
        },
        {
          "unitId": "E4",
          "variantId": "bandit_archer",
          "position": {
            "x": 15,
            "y": 11
          }
        },
        {
          "unitId": "E5",
          "variantId": "scout",
          "position": {
            "x": 15,
            "y": 8
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    },
    {
      "id": "mixed_patrol",
      "displayName": "Mixed Patrol",
      "description": "Guards leading a mixed ranged patrol.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "guard",
          "position": {
            "x": 14,
            "y": 7
          }
        },
        {
          "unitId": "E2",
          "variantId": "guard",
          "position": {
            "x": 14,
            "y": 9
          }
        },
        {
          "unitId": "E3",
          "variantId": "goblin_archer",
          "position": {
            "x": 15,
            "y": 5
          }
        },
        {
          "unitId": "E4",
          "variantId": "goblin_archer",
          "position": {
            "x": 15,
            "y": 11
          }
        },
        {
          "unitId": "E5",
          "variantId": "bandit_melee",
          "position": {
            "x": 14,
            "y": 8
          }
        },
        {
          "unitId": "E6",
          "variantId": "scout",
          "position": {
            "x": 15,
            "y": 8
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    },
    {
      "id": "orc_push",
      "displayName": "Orc Push",
      "description": "Orc front line with goblin ranged support.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "orc_warrior",
          "position": {
            "x": 13,
            "y": 6
          }
        },
        {
          "unitId": "E2",
          "variantId": "orc_warrior",
          "position": {
            "x": 13,
            "y": 8
          }
        },
        {
          "unitId": "E3",
          "variantId": "orc_warrior",
          "position": {
            "x": 13,
            "y": 10
          }
        },
        {
          "unitId": "E4",
          "variantId": "orc_warrior",
          "position": {
            "x": 14,
            "y": 8
          }
        },
        {
          "unitId": "E5",
          "variantId": "goblin_archer",
          "position": {
            "x": 15,
            "y": 6
          }
        },
        {
          "unitId": "E6",
          "variantId": "goblin_archer",
          "position": {
            "x": 15,
            "y": 10
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    },
    {
      "id": "wolf_harriers",
      "displayName": "Wolf Harriers",
      "description": "Wolves rushing ahead of goblin support fire.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "wolf",
          "position": {
            "x": 13,
            "y": 6
          }
        },
        {
          "unitId": "E2",
          "variantId": "wolf",
          "position": {
            "x": 13,
            "y": 8
          }
        },
        {
          "unitId": "E3",
          "variantId": "wolf",
          "position": {
            "x": 13,
            "y": 10
          }
        },
        {
          "unitId": "E7",
          "variantId": "wolf",
          "position": {
            "x": 13,
            "y": 12
          }
        },
        {
          "unitId": "E4",
          "variantId": "goblin_archer",
          "position": {
            "x": 15,
            "y": 6
          }
        },
        {
          "unitId": "E5",
          "variantId": "goblin_archer",
          "position": {
            "x": 15,
            "y": 10
          }
        },
        {
          "unitId": "E6",
          "variantId": "goblin_raider",
          "position": {
            "x": 14,
            "y": 8
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    },
    {
      "id": "marsh_predators",
      "displayName": "Marsh Predators",
      "description": "Two giant toads backed by three crocodiles clustered along the marsh edge.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "giant_toad",
          "position": {
            "x": 9,
            "y": 7
          }
        },
        {
          "unitId": "E2",
          "variantId": "crocodile",
          "position": {
            "x": 1,
            "y": 1
          }
        },
        {
          "unitId": "E3",
          "variantId": "crocodile",
          "position": {
            "x": 4,
            "y": 1
          }
        },
        {
          "unitId": "E4",
          "variantId": "crocodile",
          "position": {
            "x": 2,
            "y": 4
          }
        },
        {
          "unitId": "E5",
          "variantId": "giant_toad",
          "position": {
            "x": 9,
            "y": 10
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    },
    {
      "id": "hobgoblin_kill_box",
      "displayName": "Hobgoblin Kill Box",
      "description": "A hobgoblin shield line locking lanes for archers and a goblin boss.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "hobgoblin_warrior",
          "position": {
            "x": 10,
            "y": 5
          }
        },
        {
          "unitId": "E2",
          "variantId": "hobgoblin_warrior",
          "position": {
            "x": 10,
            "y": 8
          }
        },
        {
          "unitId": "E3",
          "variantId": "hobgoblin_warrior",
          "position": {
            "x": 10,
            "y": 11
          }
        },
        {
          "unitId": "E4",
          "variantId": "hobgoblin_warrior",
          "position": {
            "x": 12,
            "y": 8
          }
        },
        {
          "unitId": "E5",
          "variantId": "hobgoblin_archer",
          "position": {
            "x": 14,
            "y": 5
          }
        },
        {
          "unitId": "E6",
          "variantId": "hobgoblin_archer",
          "position": {
            "x": 14,
            "y": 8
          }
        },
        {
          "unitId": "E7",
          "variantId": "hobgoblin_archer",
          "position": {
            "x": 14,
            "y": 11
          }
        },
        {
          "unitId": "E8",
          "variantId": "goblin_boss",
          "position": {
            "x": 13,
            "y": 8
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    },
    {
      "id": "predator_rampage",
      "displayName": "Predator Rampage",
      "description": "Dire wolves and worgs crash in ahead of gnoll bows and a giant hyena finisher.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "dire_wolf",
          "position": {
            "x": 10,
            "y": 5
          }
        },
        {
          "unitId": "E2",
          "variantId": "dire_wolf",
          "position": {
            "x": 10,
            "y": 10
          }
        },
        {
          "unitId": "E3",
          "variantId": "giant_hyena",
          "position": {
            "x": 12,
            "y": 7
          }
        },
        {
          "unitId": "E4",
          "variantId": "gnoll_warrior",
          "position": {
            "x": 14,
            "y": 6
          }
        },
        {
          "unitId": "E5",
          "variantId": "gnoll_warrior",
          "position": {
            "x": 14,
            "y": 10
          }
        },
        {
          "unitId": "E6",
          "variantId": "worg",
          "position": {
            "x": 12,
            "y": 10
          }
        },
        {
          "unitId": "E7",
          "variantId": "worg",
          "position": {
            "x": 12,
            "y": 2
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    },
    {
      "id": "bugbear_dragnet",
      "displayName": "Bugbear Dragnet",
      "description": "Bugbears pin the front while a goblin boss and archers punish the approach lanes.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "bugbear_warrior",
          "position": {
            "x": 10,
            "y": 6
          }
        },
        {
          "unitId": "E2",
          "variantId": "bugbear_warrior",
          "position": {
            "x": 10,
            "y": 10
          }
        },
        {
          "unitId": "E3",
          "variantId": "goblin_boss",
          "position": {
            "x": 13,
            "y": 8
          }
        },
        {
          "unitId": "E4",
          "variantId": "goblin_archer",
          "position": {
            "x": 14,
            "y": 7
          }
        },
        {
          "unitId": "E5",
          "variantId": "goblin_minion",
          "position": {
            "x": 14,
            "y": 9
          }
        },
        {
          "unitId": "E6",
          "variantId": "hobgoblin_archer",
          "position": {
            "x": 15,
            "y": 5
          }
        },
        {
          "unitId": "E7",
          "variantId": "hobgoblin_archer",
          "position": {
            "x": 15,
            "y": 11
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    },
    {
      "id": "deadwatch_phalanx",
      "displayName": "Deadwatch Phalanx",
      "description": "Animated armor and undead archers grind attackers down behind a rigid phalanx.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "animated_armor",
          "position": {
            "x": 10,
            "y": 6
          }
        },
        {
          "unitId": "E2",
          "variantId": "animated_armor",
          "position": {
            "x": 10,
            "y": 10
          }
        },
        {
          "unitId": "E3",
          "variantId": "zombie",
          "position": {
            "x": 12,
            "y": 5
          }
        },
        {
          "unitId": "E4",
          "variantId": "zombie",
          "position": {
            "x": 12,
            "y": 11
          }
        },
        {
          "unitId": "E5",
          "variantId": "skeleton",
          "position": {
            "x": 15,
            "y": 4
          }
        },
        {
          "unitId": "E6",
          "variantId": "skeleton",
          "position": {
            "x": 15,
            "y": 7
          }
        },
        {
          "unitId": "E7",
          "variantId": "skeleton",
          "position": {
            "x": 15,
            "y": 10
          }
        },
        {
          "unitId": "E8",
          "variantId": "skeleton",
          "position": {
            "x": 15,
            "y": 13
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    },
    {
      "id": "captains_crossfire",
      "displayName": "Captain's Crossfire",
      "description": "A veteran captain anchors a layered crossfire with guard screens and parrying nobles.",
      "units": [
        {
          "unitId": "E1",
          "variantId": "guard",
          "position": {
            "x": 10,
            "y": 7
          }
        },
        {
          "unitId": "E2",
          "variantId": "guard",
          "position": {
            "x": 10,
            "y": 9
          }
        },
        {
          "unitId": "E3",
          "variantId": "bandit_captain",
          "position": {
            "x": 11,
            "y": 8
          }
        },
        {
          "unitId": "E4",
          "variantId": "noble",
          "position": {
            "x": 12,
            "y": 6
          }
        },
        {
          "unitId": "E5",
          "variantId": "noble",
          "position": {
            "x": 12,
            "y": 10
          }
        },
        {
          "unitId": "E6",
          "variantId": "scout",
          "position": {
            "x": 14,
            "y": 4
          }
        },
        {
          "unitId": "E7",
          "variantId": "scout",
          "position": {
            "x": 14,
            "y": 12
          }
        }
      ],
      "terrainFeatures": [
        {
          "featureId": "rock_1",
          "kind": "rock",
          "position": {
            "x": 5,
            "y": 8
          },
          "footprint": {
            "width": 1,
            "height": 1
          }
        }
      ]
    }
  ]
};

const TEST_PLAYER_CATALOG: PlayerCatalogResponse = {
  "defaultPlayerPresetId": "martial_mixed_party",
  "classes": [
    {
      "id": "barbarian",
      "displayName": "Barbarian",
      "category": "martial",
      "maxSupportedLevel": 2
    },
    {
      "id": "fighter",
      "displayName": "Fighter",
      "category": "martial",
      "maxSupportedLevel": 5
    },
    {
      "id": "monk",
      "displayName": "Monk",
      "category": "martial",
      "maxSupportedLevel": 2
    },
    {
      "id": "paladin",
      "displayName": "Paladin",
      "category": "half_caster",
      "maxSupportedLevel": 5
    },
    {
      "id": "rogue",
      "displayName": "Rogue",
      "category": "martial",
      "maxSupportedLevel": 5
    },
    {
      "id": "wizard",
      "displayName": "Wizard",
      "category": "spellcaster",
      "maxSupportedLevel": 1
    }
  ],
  "loadouts": [
    {
      "id": "barbarian_sample_build",
      "displayName": "Level 1 Barbarian Sample Build",
      "classId": "barbarian",
      "level": 1,
      "maxHp": 15,
      "featureIds": [
        "rage",
        "unarmored_defense",
        "weapon_mastery_cleave",
        "weapon_mastery_vex"
      ],
      "weaponIds": [
        "greataxe",
        "handaxe"
      ]
    },
    {
      "id": "barbarian_level2_sample_build",
      "displayName": "Level 2 Barbarian Sample Build",
      "classId": "barbarian",
      "level": 2,
      "maxHp": 25,
      "featureIds": [
        "rage",
        "unarmored_defense",
        "reckless_attack",
        "danger_sense",
        "weapon_mastery_cleave",
        "weapon_mastery_vex"
      ],
      "weaponIds": [
        "greataxe",
        "handaxe"
      ]
    },
    {
      "id": "fighter_sample_build",
      "displayName": "Level 1 Fighter Sample Build",
      "classId": "fighter",
      "level": 1,
      "maxHp": 13,
      "featureIds": [
        "second_wind",
        "great_weapon_fighting",
        "savage_attacker",
        "weapon_mastery_graze",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "flail",
        "greatsword",
        "javelin"
      ]
    },
    {
      "id": "fighter_level2_benchmark_tank",
      "displayName": "Level 2 Fighter Benchmark Tank",
      "classId": "fighter",
      "level": 2,
      "maxHp": 100,
      "featureIds": [
        "second_wind",
        "action_surge",
        "great_weapon_fighting",
        "savage_attacker",
        "weapon_mastery_graze",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "flail",
        "greatsword",
        "javelin"
      ]
    },
    {
      "id": "fighter_level2_sample_build",
      "displayName": "Level 2 Fighter Sample Build",
      "classId": "fighter",
      "level": 2,
      "maxHp": 21,
      "featureIds": [
        "second_wind",
        "action_surge",
        "great_weapon_fighting",
        "savage_attacker",
        "weapon_mastery_graze",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "flail",
        "greatsword",
        "javelin"
      ]
    },
    {
      "id": "fighter_level3_sample_build",
      "displayName": "Level 3 Fighter Battle Master Sample Build",
      "classId": "fighter",
      "level": 3,
      "maxHp": 29,
      "featureIds": [
        "second_wind",
        "action_surge",
        "combat_superiority",
        "student_of_war",
        "great_weapon_fighting",
        "savage_attacker",
        "weapon_mastery_graze",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "flail",
        "greatsword",
        "javelin"
      ]
    },
    {
      "id": "fighter_level4_sample_build",
      "displayName": "Level 4 Fighter Battle Master Sample Build",
      "classId": "fighter",
      "level": 4,
      "maxHp": 37,
      "featureIds": [
        "second_wind",
        "action_surge",
        "combat_superiority",
        "student_of_war",
        "great_weapon_master",
        "great_weapon_fighting",
        "savage_attacker",
        "weapon_mastery_graze",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "flail",
        "greatsword",
        "javelin"
      ]
    },
    {
      "id": "fighter_level5_sample_build",
      "displayName": "Level 5 Fighter Battle Master Sample Build",
      "classId": "fighter",
      "level": 5,
      "maxHp": 45,
      "featureIds": [
        "second_wind",
        "action_surge",
        "combat_superiority",
        "student_of_war",
        "great_weapon_master",
        "extra_attack",
        "tactical_shift",
        "great_weapon_fighting",
        "savage_attacker",
        "weapon_mastery_graze",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "flail",
        "greatsword",
        "javelin"
      ]
    },
    {
      "id": "monk_sample_build",
      "displayName": "Level 1 Monk Sample Build",
      "classId": "monk",
      "level": 1,
      "maxHp": 10,
      "featureIds": [
        "martial_arts",
        "unarmored_defense"
      ],
      "weaponIds": [
        "shortsword",
        "unarmed_strike"
      ]
    },
    {
      "id": "monk_level2_sample_build",
      "displayName": "Level 2 Monk Sample Build",
      "classId": "monk",
      "level": 2,
      "maxHp": 18,
      "featureIds": [
        "martial_arts",
        "unarmored_defense",
        "monks_focus",
        "unarmored_movement",
        "uncanny_metabolism"
      ],
      "weaponIds": [
        "shortsword",
        "unarmed_strike"
      ]
    },
    {
      "id": "paladin_level1_sample_build",
      "displayName": "Level 1 Paladin Sample Build",
      "classId": "paladin",
      "level": 1,
      "maxHp": 13,
      "featureIds": [
        "lay_on_hands",
        "spellcasting",
        "weapon_mastery",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "javelin",
        "longsword"
      ]
    },
    {
      "id": "paladin_level2_sample_build",
      "displayName": "Level 2 Paladin Sample Build",
      "classId": "paladin",
      "level": 2,
      "maxHp": 22,
      "featureIds": [
        "lay_on_hands",
        "spellcasting",
        "weapon_mastery",
        "fighting_style_defense",
        "paladins_smite",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "javelin",
        "longsword"
      ]
    },
    {
      "id": "paladin_level3_sample_build",
      "displayName": "Level 3 Paladin Sample Build",
      "classId": "paladin",
      "level": 3,
      "maxHp": 31,
      "featureIds": [
        "lay_on_hands",
        "spellcasting",
        "weapon_mastery",
        "fighting_style_defense",
        "paladins_smite",
        "channel_divinity",
        "oath_of_the_ancients",
        "natures_wrath",
        "oath_spells_ancients",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "javelin",
        "longsword"
      ]
    },
    {
      "id": "paladin_level4_sample_build",
      "displayName": "Level 4 Paladin Sample Build",
      "classId": "paladin",
      "level": 4,
      "maxHp": 40,
      "featureIds": [
        "lay_on_hands",
        "spellcasting",
        "weapon_mastery",
        "fighting_style_defense",
        "paladins_smite",
        "channel_divinity",
        "oath_of_the_ancients",
        "natures_wrath",
        "oath_spells_ancients",
        "sentinel",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "javelin",
        "longsword"
      ]
    },
    {
      "id": "paladin_level5_sample_build",
      "displayName": "Level 5 Paladin Sample Build",
      "classId": "paladin",
      "level": 5,
      "maxHp": 49,
      "featureIds": [
        "lay_on_hands",
        "spellcasting",
        "weapon_mastery",
        "fighting_style_defense",
        "paladins_smite",
        "channel_divinity",
        "oath_of_the_ancients",
        "natures_wrath",
        "oath_spells_ancients",
        "sentinel",
        "extra_attack",
        "faithful_steed",
        "weapon_mastery_sap",
        "weapon_mastery_slow"
      ],
      "weaponIds": [
        "javelin",
        "longsword"
      ]
    },
    {
      "id": "rogue_melee_sample_build",
      "displayName": "Melee Rogue Sample Build",
      "classId": "rogue",
      "level": 1,
      "maxHp": 10,
      "featureIds": [
        "sneak_attack"
      ],
      "weaponIds": [
        "rapier",
        "shortbow"
      ]
    },
    {
      "id": "rogue_ranged_sample_build",
      "displayName": "Ranged Rogue Sample Build",
      "classId": "rogue",
      "level": 1,
      "maxHp": 10,
      "featureIds": [
        "sneak_attack"
      ],
      "weaponIds": [
        "shortbow",
        "shortsword"
      ]
    },
    {
      "id": "rogue_melee_level2_sample_build",
      "displayName": "Level 2 Melee Rogue Sample Build",
      "classId": "rogue",
      "level": 2,
      "maxHp": 18,
      "featureIds": [
        "sneak_attack",
        "cunning_action"
      ],
      "weaponIds": [
        "rapier",
        "shortbow"
      ]
    },
    {
      "id": "rogue_ranged_level2_benchmark_archer",
      "displayName": "Level 2 Ranged Rogue Benchmark Archer",
      "classId": "rogue",
      "level": 2,
      "maxHp": 50,
      "featureIds": [
        "sneak_attack",
        "cunning_action"
      ],
      "weaponIds": [
        "shortbow",
        "shortsword"
      ]
    },
    {
      "id": "rogue_ranged_level2_sample_build",
      "displayName": "Level 2 Ranged Rogue Sample Build",
      "classId": "rogue",
      "level": 2,
      "maxHp": 18,
      "featureIds": [
        "sneak_attack",
        "cunning_action"
      ],
      "weaponIds": [
        "shortbow",
        "shortsword"
      ]
    },
    {
      "id": "rogue_ranged_level3_assassin_sample_build",
      "displayName": "Level 3 Ranged Assassin Rogue Sample Build",
      "classId": "rogue",
      "level": 3,
      "maxHp": 26,
      "featureIds": [
        "sneak_attack",
        "expertise_stealth",
        "cunning_action",
        "steady_aim",
        "assassinate",
        "assassin_tools"
      ],
      "weaponIds": [
        "shortbow",
        "shortsword"
      ]
    },
    {
      "id": "rogue_ranged_level4_assassin_sample_build",
      "displayName": "Level 4 Ranged Assassin Rogue Sample Build",
      "classId": "rogue",
      "level": 4,
      "maxHp": 34,
      "featureIds": [
        "sneak_attack",
        "expertise_stealth",
        "cunning_action",
        "steady_aim",
        "assassinate",
        "assassin_tools",
        "sharpshooter"
      ],
      "weaponIds": [
        "shortbow",
        "shortsword"
      ]
    },
    {
      "id": "rogue_ranged_level5_assassin_sample_build",
      "displayName": "Level 5 Ranged Assassin Rogue Sample Build",
      "classId": "rogue",
      "level": 5,
      "maxHp": 42,
      "featureIds": [
        "sneak_attack",
        "expertise_stealth",
        "cunning_action",
        "steady_aim",
        "assassinate",
        "assassin_tools",
        "sharpshooter",
        "cunning_strike",
        "uncanny_dodge"
      ],
      "weaponIds": [
        "shortbow",
        "shortsword"
      ]
    },
    {
      "id": "wizard_sample_build",
      "displayName": "Level 1 Wizard Sample Build",
      "classId": "wizard",
      "level": 1,
      "maxHp": 8,
      "featureIds": [
        "spellcasting",
        "ritual_adept",
        "arcane_recovery"
      ],
      "weaponIds": [
        "dagger"
      ]
    }
  ],
  "playerPresets": [
    {
      "id": "fighter_sample_trio",
      "displayName": "Level 1 Fighter Trio",
      "description": "Three level 1 fighters using the original proof-of-concept build.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "fighter_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "fighter_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "fighter_sample_build"
        }
      ]
    },
    {
      "id": "fighter_level2_sample_trio",
      "displayName": "Level 2 Fighter Trio",
      "description": "Three level 2 great-weapon fighters with Action Surge.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "fighter_level2_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "fighter_level2_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "fighter_level2_sample_build"
        }
      ]
    },
    {
      "id": "fighter_level3_sample_trio",
      "displayName": "Level 3 Fighter Battle Master Trio",
      "description": "Three level 3 great-weapon Battle Master fighters with Superiority Dice.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "fighter_level3_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "fighter_level3_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "fighter_level3_sample_build"
        }
      ]
    },
    {
      "id": "fighter_level4_sample_trio",
      "displayName": "Level 4 Fighter Battle Master Trio",
      "description": "Three level 4 great-weapon Battle Master fighters with Great Weapon Master.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "fighter_level4_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "fighter_level4_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "fighter_level4_sample_build"
        }
      ]
    },
    {
      "id": "fighter_level5_sample_trio",
      "displayName": "Level 5 Fighter Battle Master Trio",
      "description": "Three level 5 great-weapon Battle Master fighters with Extra Attack and Tactical Shift.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "fighter_level5_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "fighter_level5_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "fighter_level5_sample_build"
        }
      ]
    },
    {
      "id": "rogue_ranged_trio",
      "displayName": "Ranged Rogue Trio",
      "description": "Three level 1 ranged rogues with shortbows and shortsword fallback.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "rogue_ranged_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "rogue_ranged_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "rogue_ranged_sample_build"
        }
      ]
    },
    {
      "id": "rogue_melee_trio",
      "displayName": "Melee Rogue Trio",
      "description": "Three level 1 melee rogues with rapiers and shortbow fallback.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "rogue_melee_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "rogue_melee_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "rogue_melee_sample_build"
        }
      ]
    },
    {
      "id": "rogue_level2_ranged_trio",
      "displayName": "Level 2 Ranged Rogue Trio",
      "description": "Three level 2 ranged rogues with shortbows, Cunning Action, and shortsword fallback.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "rogue_ranged_level2_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "rogue_ranged_level2_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "rogue_ranged_level2_sample_build"
        }
      ]
    },
    {
      "id": "rogue_level2_melee_trio",
      "displayName": "Level 2 Melee Rogue Trio",
      "description": "Three level 2 melee rogues with rapiers, Cunning Action, and shortbow fallback.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "rogue_melee_level2_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "rogue_melee_level2_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "rogue_melee_level2_sample_build"
        }
      ]
    },
    {
      "id": "rogue_level3_ranged_assassin_trio",
      "displayName": "Level 3 Ranged Assassin Rogue Trio",
      "description": "Three level 3 ranged Assassin rogues with shortbows, Steady Aim, and Assassinate.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "rogue_ranged_level3_assassin_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "rogue_ranged_level3_assassin_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "rogue_ranged_level3_assassin_sample_build"
        }
      ]
    },
    {
      "id": "rogue_level4_ranged_assassin_trio",
      "displayName": "Level 4 Ranged Assassin Rogue Trio",
      "description": "Three level 4 ranged Assassin rogues with shortbows, Sharpshooter, Steady Aim, and Assassinate.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "rogue_ranged_level4_assassin_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "rogue_ranged_level4_assassin_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "rogue_ranged_level4_assassin_sample_build"
        }
      ]
    },
    {
      "id": "rogue_level5_ranged_assassin_trio",
      "displayName": "Level 5 Ranged Assassin Rogue Trio",
      "description": "Three level 5 ranged Assassin rogues with shortbows, Cunning Strike, and Uncanny Dodge.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "rogue_ranged_level5_assassin_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "rogue_ranged_level5_assassin_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "rogue_ranged_level5_assassin_sample_build"
        }
      ]
    },
    {
      "id": "barbarian_sample_trio",
      "displayName": "Level 1 Barbarian Trio",
      "description": "Three level 1 barbarians with greataxes and thrown handaxe fallback.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "barbarian_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "barbarian_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "barbarian_sample_build"
        }
      ]
    },
    {
      "id": "barbarian_level2_sample_trio",
      "displayName": "Level 2 Barbarian Trio",
      "description": "Three level 2 barbarians with greataxes, handaxes, Reckless Attack, and Danger Sense.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "barbarian_level2_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "barbarian_level2_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "barbarian_level2_sample_build"
        }
      ]
    },
    {
      "id": "monk_sample_trio",
      "displayName": "Level 1 Monk Trio",
      "description": "Three level 1 monks with shortswords, Martial Arts, and Unarmored Defense.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "monk_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "monk_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "monk_sample_build"
        }
      ]
    },
    {
      "id": "monk_level2_sample_trio",
      "displayName": "Level 2 Monk Trio",
      "description": "Three level 2 monks with Focus, Unarmored Movement, and Uncanny Metabolism.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "monk_level2_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "monk_level2_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "monk_level2_sample_build"
        }
      ]
    },
    {
      "id": "paladin_level1_sample_trio",
      "displayName": "Level 1 Paladin Trio",
      "description": "Three level 1 plate-and-shield paladins with Bless, Cure Wounds, and Lay on Hands.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "paladin_level1_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "paladin_level1_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "paladin_level1_sample_build"
        }
      ]
    },
    {
      "id": "paladin_level2_sample_trio",
      "displayName": "Level 2 Paladin Trio",
      "description": "Three level 2 plate-and-shield paladins with Defense, Divine Smite, Bless, and Lay on Hands.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "paladin_level2_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "paladin_level2_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "paladin_level2_sample_build"
        }
      ]
    },
    {
      "id": "paladin_level3_sample_trio",
      "displayName": "Level 3 Paladin Trio",
      "description": "Three level 3 Oath of the Ancients paladins with Nature's Wrath.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "paladin_level3_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "paladin_level3_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "paladin_level3_sample_build"
        }
      ]
    },
    {
      "id": "paladin_level4_sample_trio",
      "displayName": "Level 4 Paladin Trio",
      "description": "Three level 4 Oath of the Ancients paladins with Sentinel.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "paladin_level4_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "paladin_level4_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "paladin_level4_sample_build"
        }
      ]
    },
    {
      "id": "paladin_level5_sample_trio",
      "displayName": "Level 5 Paladin Trio",
      "description": "Three level 5 Oath of the Ancients paladins with Extra Attack, level 2 Bless, and Aid rules support.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "paladin_level5_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "paladin_level5_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "paladin_level5_sample_build"
        }
      ]
    },
    {
      "id": "wizard_sample_trio",
      "displayName": "Level 1 Wizard Trio",
      "description": "Three level 1 wizards with direct damage, melee escape, Shield, and Burning Hands pressure.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "wizard_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "wizard_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "wizard_sample_build"
        }
      ]
    },
    {
      "id": "martial_mixed_party",
      "displayName": "Mixed Martial Party",
      "description": "One level 5 Battle Master fighter, one level 5 Paladin, one level 5 ranged Assassin rogue, and one level 1 wizard.",
      "units": [
        {
          "unitId": "F1",
          "loadoutId": "fighter_level5_sample_build"
        },
        {
          "unitId": "F2",
          "loadoutId": "paladin_level5_sample_build"
        },
        {
          "unitId": "F3",
          "loadoutId": "rogue_ranged_level5_assassin_sample_build"
        },
        {
          "unitId": "F4",
          "loadoutId": "wizard_sample_build"
        }
      ]
    }
  ]
};

const ACTIVE_ENEMY_PRESET_IDS = [
  'goblin_screen',
  'bandit_ambush',
  'mixed_patrol',
  'orc_push',
  'wolf_harriers',
  'marsh_predators',
  'hobgoblin_kill_box',
  'predator_rampage',
  'bugbear_dragnet',
  'deadwatch_phalanx',
  'captains_crossfire',
];

const ACTIVE_PLAYER_PRESET_IDS = [
  'fighter_sample_trio',
  'fighter_level2_sample_trio',
  'fighter_level3_sample_trio',
  'fighter_level4_sample_trio',
  'fighter_level5_sample_trio',
  'rogue_ranged_trio',
  'rogue_melee_trio',
  'rogue_level2_ranged_trio',
  'rogue_level2_melee_trio',
  'rogue_level3_ranged_assassin_trio',
  'rogue_level4_ranged_assassin_trio',
  'rogue_level5_ranged_assassin_trio',
  'barbarian_sample_trio',
  'barbarian_level2_sample_trio',
  'monk_sample_trio',
  'monk_level2_sample_trio',
  'paladin_level1_sample_trio',
  'paladin_level2_sample_trio',
  'paladin_level3_sample_trio',
  'paladin_level4_sample_trio',
  'paladin_level5_sample_trio',
  'wizard_sample_trio',
  'martial_mixed_party',
];

const FIXED_ROCK_TERRAIN = {
  featureId: 'rock_1',
  kind: 'rock',
  position: { x: 5, y: 8 },
  footprint: { width: 1, height: 1 },
};

const CURRENT_MARSH_PREDATORS_UNITS = [
  { unitId: 'E1', variantId: 'giant_toad', position: { x: 9, y: 7 } },
  { unitId: 'E2', variantId: 'crocodile', position: { x: 1, y: 1 } },
  { unitId: 'E3', variantId: 'crocodile', position: { x: 4, y: 1 } },
  { unitId: 'E4', variantId: 'crocodile', position: { x: 2, y: 4 } },
  { unitId: 'E5', variantId: 'giant_toad', position: { x: 9, y: 10 } },
];

function buildUnit(
  id: string,
  templateName: string,
  faction: 'fighters' | 'goblins',
  combatRole: UnitState['combatRole'],
  position: GridPosition,
  maxHp: number,
): UnitState {
  return {
    id,
    faction,
    combatRole,
    templateName,
    roleTags: [],
    currentHp: maxHp,
    maxHp,
    temporaryHitPoints: 0,
    ac: faction === 'fighters' ? 16 : 15,
    speed: 30,
    effectiveSpeed: 30,
    initiativeMod: faction === 'fighters' ? 1 : 2,
    initiativeScore: 12,
    abilityMods: {
      str: 3,
      dex: 1,
      con: 2,
      int: 0,
      wis: 0,
      cha: 0,
    },
    passivePerception: 10,
    sizeCategory: faction === 'fighters' ? 'medium' : 'small',
    footprint: { width: 1, height: 1 },
    conditions: {
      unconscious: false,
      prone: false,
      dead: false,
    },
    deathSaveSuccesses: 0,
    deathSaveFailures: 0,
    stable: false,
    resources: {
      secondWindUses: faction === 'fighters' ? 1 : 0,
      javelins: faction === 'fighters' ? 6 : 0,
      rageUses: 0,
      handaxes: 0,
      actionSurgeUses: 0,
      superiorityDice: 0,
      focusPoints: 0,
      uncannyMetabolismUses: 0,
      spellSlotsLevel1: 0,
      spellSlotsLevel2: 0,
      layOnHandsPoints: 0,
      channelDivinityUses: 0,
    },
    position,
    temporaryEffects: [],
    reactionAvailable: true,
    attacks: {} as UnitState['attacks'],
    medicineModifier: 0,
  };
}

function buildEncounterState(
  seed: string,
  playerBehavior: EncounterState['playerBehavior'],
  monsterBehavior: EncounterState['monsterBehavior'],
  combatLogLength: number,
): EncounterState {
  const units: Record<string, UnitState> = {
    F1: buildUnit('F1', 'Level 2 Fighter Sample Build', 'fighters', 'fighter', { x: 1, y: 7 }, 21),
    F2: buildUnit('F2', 'Level 4 Paladin Sample Build', 'fighters', 'paladin', { x: 1, y: 8 }, 40),
    F3: buildUnit('F3', 'Level 5 Ranged Assassin Rogue Sample Build', 'fighters', 'rogue', { x: 1, y: 9 }, 42),
    F4: buildUnit('F4', 'Level 2 Melee Rogue Sample Build', 'fighters', 'rogue', { x: 1, y: 10 }, 18),
    E1: buildUnit('E1', '2024 Goblin Raider', 'goblins', 'goblin_melee', { x: 14, y: 6 }, 10),
    E2: buildUnit('E2', '2024 Goblin Raider', 'goblins', 'goblin_melee', { x: 14, y: 8 }, 10),
    E3: buildUnit('E3', '2024 Goblin Raider', 'goblins', 'goblin_melee', { x: 14, y: 10 }, 10),
    E4: buildUnit('E4', '2024 Goblin Archer', 'goblins', 'goblin_archer', { x: 15, y: 5 }, 10),
    E5: buildUnit('E5', '2024 Goblin Archer', 'goblins', 'goblin_archer', { x: 15, y: 8 }, 10),
    E6: buildUnit('E6', '2024 Goblin Archer', 'goblins', 'goblin_archer', { x: 15, y: 11 }, 10),
  };
  units.F1.resources.actionSurgeUses = 1;
  units.F2.ac = 21;
  units.F2.resources.secondWindUses = 0;
  units.F2.resources.javelins = 0;
  units.F2.resources.spellSlotsLevel1 = 4;
  units.F2.resources.spellSlotsLevel2 = 2;
  units.F2.resources.layOnHandsPoints = 25;
  units.F2.resources.channelDivinityUses = 2;

  const combatLog: CombatEvent[] = Array.from({ length: combatLogLength }, (_, index): CombatEvent => ({
    round: 1,
    actorId: 'F1',
    targetIds: ['E1'],
    eventType: index === 0 ? 'move' : 'attack',
    rawRolls: index === 0 ? {} : { attackRoll: 14 },
    resolvedTotals: index === 0 ? { movementPhase: 'before_action' } : { total: 19 },
    movementDetails:
      index === 0
        ? {
            start: { x: 1, y: 7 },
            end: { x: 3, y: 7 },
            path: [
              { x: 1, y: 7 },
              { x: 2, y: 7 },
              { x: 3, y: 7 },
            ],
            distance: 2,
          }
        : null,
    damageDetails: null,
    conditionDeltas: [],
    textSummary: index === 0 ? 'F1 moves into range.' : 'F1 attacks E1.',
  }));

  return {
    seed,
    playerBehavior,
    monsterBehavior,
    rngState: 123456,
    round: 1,
    initiativeOrder: ['F1', 'F2', 'F3', 'F4', 'E1', 'E2', 'E3', 'E4', 'E5', 'E6'],
    initiativeScores: {
      F1: 15,
      F2: 14,
      F3: 13,
      F4: 12,
      E1: 12,
      E2: 12,
      E3: 12,
      E4: 12,
      E5: 12,
      E6: 12,
    },
    activeCombatantIndex: 0,
    units,
    combatLog,
    winner: null,
    terminalState: 'ongoing',
    rescueSubphase: false,
  };
}

function buildEncounterResult(config: EncounterConfig): RunEncounterResult {
  const finalState = buildEncounterState(
    config.seed,
    config.playerBehavior === 'dumb' ? 'dumb' : 'smart',
    config.monsterBehavior === 'kind' ? 'kind' : config.monsterBehavior === 'evil' ? 'evil' : 'balanced',
    2,
  );

  const firstFrame: ReplayFrame = {
    index: 0,
    round: 1,
    activeCombatantId: 'F1',
    state: buildEncounterState(finalState.seed, finalState.playerBehavior, finalState.monsterBehavior, 1),
    events: [
      {
        round: 1,
        actorId: 'F1',
        targetIds: ['E1'],
        eventType: 'move',
        rawRolls: {},
        resolvedTotals: { movementPhase: 'before_action' },
        movementDetails: {
          start: { x: 1, y: 7 },
          end: { x: 3, y: 7 },
          path: [
            { x: 1, y: 7 },
            { x: 2, y: 7 },
            { x: 3, y: 7 },
          ],
          distance: 2,
        },
        damageDetails: null,
        conditionDeltas: [],
        textSummary: 'F1 moves into range.',
      },
    ],
  };

  const secondFrame: ReplayFrame = {
    index: 1,
    round: 1,
    activeCombatantId: 'F1',
    state: finalState,
    events: [
      {
        round: 1,
        actorId: 'F1',
        targetIds: ['E1'],
        eventType: 'attack',
        rawRolls: { attackRoll: 14 },
        resolvedTotals: { total: 19 },
        movementDetails: null,
        damageDetails: null,
        conditionDeltas: [],
        textSummary: 'F1 attacks E1.',
      },
    ],
  };

  return {
    finalState,
    events: [...firstFrame.events, ...secondFrame.events],
    replayFrames: [firstFrame, secondFrame],
  };
}

function buildBatchSummary(config: EncounterConfig): BatchSummary {
  const batchSize = config.batchSize ?? 100;
  const playerBehavior = config.playerBehavior ?? 'balanced';
  const monsterBehavior = config.monsterBehavior ?? 'combined';

  if (monsterBehavior === 'combined') {
    return {
      seed: config.seed,
      playerBehavior,
      monsterBehavior: 'combined',
      batchSize,
      totalRuns: batchSize * 3,
      playerWinRate: 0.35,
      goblinWinRate: 0.65,
      mutualAnnihilationRate: 0,
      smartPlayerWinRate: 0.42,
      dumbPlayerWinRate: 0.28,
      smartRunCount: Math.ceil((batchSize * 3) / 2),
      dumbRunCount: Math.floor((batchSize * 3) / 2),
      averageRounds: 6.5,
      averageFighterDeaths: 1.2,
      averageGoblinsKilled: 3.7,
      averageRemainingFighterHp: 7.4,
      averageRemainingGoblinHp: 28.1,
      stableButUnconsciousCount: 4,
      combinationSummaries: [
        {
          seed: config.seed,
          playerBehavior,
          monsterBehavior: 'kind',
          batchSize,
          totalRuns: batchSize,
          playerWinRate: 0.5,
          goblinWinRate: 0.5,
          mutualAnnihilationRate: 0,
          smartPlayerWinRate: 0.6,
          dumbPlayerWinRate: 0.4,
          smartRunCount: Math.ceil(batchSize / 2),
          dumbRunCount: Math.floor(batchSize / 2),
          averageRounds: 6.1,
          averageFighterDeaths: 0.8,
          averageGoblinsKilled: 4.2,
          averageRemainingFighterHp: 10.2,
          averageRemainingGoblinHp: 18.5,
          stableButUnconsciousCount: 1,
        },
        {
          seed: config.seed,
          playerBehavior,
          monsterBehavior: 'balanced',
          batchSize,
          totalRuns: batchSize,
          playerWinRate: 0.3,
          goblinWinRate: 0.7,
          mutualAnnihilationRate: 0,
          smartPlayerWinRate: 0.4,
          dumbPlayerWinRate: 0.2,
          smartRunCount: Math.ceil(batchSize / 2),
          dumbRunCount: Math.floor(batchSize / 2),
          averageRounds: 6.7,
          averageFighterDeaths: 1.1,
          averageGoblinsKilled: 3.6,
          averageRemainingFighterHp: 6.4,
          averageRemainingGoblinHp: 29.8,
          stableButUnconsciousCount: 2,
        },
        {
          seed: config.seed,
          playerBehavior,
          monsterBehavior: 'evil',
          batchSize,
          totalRuns: batchSize,
          playerWinRate: 0.25,
          goblinWinRate: 0.75,
          mutualAnnihilationRate: 0,
          smartPlayerWinRate: 0.32,
          dumbPlayerWinRate: 0.18,
          smartRunCount: Math.ceil(batchSize / 2),
          dumbRunCount: Math.floor(batchSize / 2),
          averageRounds: 6.8,
          averageFighterDeaths: 1.5,
          averageGoblinsKilled: 3.2,
          averageRemainingFighterHp: 5.6,
          averageRemainingGoblinHp: 36.0,
          stableButUnconsciousCount: 1,
        },
      ],
    };
  }

  const smartRunCount =
    playerBehavior === 'balanced' ? Math.ceil(batchSize / 2) : playerBehavior === 'smart' ? batchSize : 0;
  const dumbRunCount =
    playerBehavior === 'balanced' ? Math.floor(batchSize / 2) : playerBehavior === 'dumb' ? batchSize : 0;

  return {
    seed: config.seed,
    playerBehavior,
    monsterBehavior,
    batchSize,
    totalRuns: batchSize,
    playerWinRate: 1,
    goblinWinRate: 0,
    mutualAnnihilationRate: 0,
    smartPlayerWinRate: smartRunCount > 0 ? 1 : null,
    dumbPlayerWinRate: dumbRunCount > 0 ? 1 : null,
    smartRunCount,
    dumbRunCount,
    averageRounds: 5,
    averageFighterDeaths: 0,
    averageGoblinsKilled: 6,
    averageRemainingFighterHp: 18,
    averageRemainingGoblinHp: 0,
    stableButUnconsciousCount: 0,
    combinationSummaries: null,
  };
}

describe('App', () => {
  beforeEach(() => {
    const batchJobs = new Map<
      string,
      {
        pollCount: number;
        summary: BatchSummary;
        startedAt: string;
        totalRuns: number;
        currentMonsterBehavior: string;
      }
    >();
    let nextBatchJobId = 1;

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const requestUrl =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.pathname
              : input.url;
        const config = init?.body ? (JSON.parse(String(init.body)) as EncounterConfig) : null;

        if (requestUrl.endsWith('/api/encounters/run')) {
          return new Response(JSON.stringify(buildEncounterResult(config!)), {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
            },
          });
        }

        if (requestUrl.endsWith('/api/encounters/batch')) {
          return new Response(JSON.stringify(buildBatchSummary(config!)), {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
            },
          });
        }

        if (requestUrl.endsWith('/api/encounters/batch-jobs')) {
          const summary = buildBatchSummary(config!);
          const jobId = `job-${nextBatchJobId}`;
          nextBatchJobId += 1;
          const startedAt = new Date().toISOString();
          const currentMonsterBehavior =
            !config?.monsterBehavior || config.monsterBehavior === 'combined' ? 'kind' : config.monsterBehavior;

          batchJobs.set(jobId, {
            pollCount: 0,
            summary,
            startedAt,
            totalRuns: summary.totalRuns,
            currentMonsterBehavior,
          });

          return new Response(
            JSON.stringify({
              jobId,
              status: 'running',
              completedRuns: 0,
              totalRuns: summary.totalRuns,
              progressRatio: 0,
              startedAt,
              finishedAt: null,
              elapsedSeconds: 0,
              currentMonsterBehavior,
              batchSummary: null,
              error: null,
            }),
            {
              status: 200,
              headers: {
                'Content-Type': 'application/json',
              },
            },
          );
        }

        if (requestUrl.endsWith('/api/catalog/enemies')) {
          return new Response(JSON.stringify(TEST_ENEMY_CATALOG), {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
            },
          });
        }

        if (requestUrl.endsWith('/api/catalog/classes')) {
          return new Response(JSON.stringify(TEST_PLAYER_CATALOG), {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
            },
          });
        }

        if (requestUrl.includes('/api/encounters/batch-jobs/')) {
          const jobId = requestUrl.split('/').pop()!;
          const job = batchJobs.get(jobId);

          if (!job) {
            return new Response(JSON.stringify({ detail: `Unknown job ${jobId}` }), {
              status: 404,
              headers: {
                'Content-Type': 'application/json',
              },
            });
          }

          job.pollCount += 1;

          if (job.pollCount === 1) {
            const completedRuns = Math.max(1, Math.ceil(job.totalRuns / 3));

            return new Response(
              JSON.stringify({
                jobId,
                status: 'running',
                completedRuns,
                totalRuns: job.totalRuns,
                progressRatio: completedRuns / job.totalRuns,
                startedAt: job.startedAt,
                finishedAt: null,
                elapsedSeconds: 1,
                currentMonsterBehavior: job.currentMonsterBehavior,
                batchSummary: null,
                error: null,
              }),
              {
                status: 200,
                headers: {
                  'Content-Type': 'application/json',
                },
              },
            );
          }

          return new Response(
            JSON.stringify({
              jobId,
              status: 'completed',
              completedRuns: job.totalRuns,
              totalRuns: job.totalRuns,
              progressRatio: 1,
              startedAt: job.startedAt,
              finishedAt: new Date().toISOString(),
              elapsedSeconds: 2,
              currentMonsterBehavior: null,
              batchSummary: job.summary,
              error: null,
            }),
            {
              status: 200,
              headers: {
                'Content-Type': 'application/json',
              },
            },
          );
        }

        return new Response(JSON.stringify({ detail: `Unexpected request to ${requestUrl}` }), {
          status: 404,
          headers: {
            'Content-Type': 'application/json',
          },
        });
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('keeps the frontend catalog gate aligned with the frozen live V4.3 surface', () => {
    expect(TEST_ENEMY_CATALOG.enemyPresets.map((preset) => preset.id)).toEqual(ACTIVE_ENEMY_PRESET_IDS);
    expect(TEST_PLAYER_CATALOG.playerPresets.map((preset) => preset.id)).toEqual(ACTIVE_PLAYER_PRESET_IDS);
    expect(TEST_PLAYER_CATALOG.classes.map((playerClass) => playerClass.id)).toEqual([
      'barbarian',
      'fighter',
      'monk',
      'paladin',
      'rogue',
      'wizard',
    ]);

    for (const preset of TEST_ENEMY_CATALOG.enemyPresets) {
      expect(preset.terrainFeatures).toEqual([FIXED_ROCK_TERRAIN]);
    }

    const marshPredators = TEST_ENEMY_CATALOG.enemyPresets.find((preset) => preset.id === 'marsh_predators');
    expect(marshPredators?.units).toEqual(CURRENT_MARSH_PREDATORS_UNITS);

    const mixedParty = TEST_PLAYER_CATALOG.playerPresets.find((preset) => preset.id === 'martial_mixed_party');
    expect(mixedParty?.units).toEqual([
      { unitId: 'F1', loadoutId: 'fighter_level5_sample_build' },
      { unitId: 'F2', loadoutId: 'paladin_level5_sample_build' },
      { unitId: 'F3', loadoutId: 'rogue_ranged_level5_assassin_sample_build' },
      { unitId: 'F4', loadoutId: 'wizard_sample_build' },
    ]);
  });

  it('opens with the default layout already loaded and ready to run', async () => {
    render(<App />);

    expect(await screen.findByText(/10 \/ 10 units placed/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /batch run/i })).toBeEnabled();
    expect(screen.getByRole('combobox', { name: /player behavior/i })).toHaveValue('balanced');
    expect(screen.getByRole('combobox', { name: /dm behavior/i })).toHaveValue('combined');
    const enemyPresetSelect = screen.getByRole('combobox', { name: /enemy preset/i });
    expect(enemyPresetSelect).toHaveValue('goblin_screen');
    expect(within(enemyPresetSelect).queryByRole('option', { name: 'Giant Toad' })).not.toBeInTheDocument();
    expect(within(enemyPresetSelect).getByRole('option', { name: 'Marsh Predators' })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /batch size/i })).toHaveValue(100);
    expect(screen.getByRole('grid', { name: /placement grid/i })).toBeInTheDocument();
  });

  it('renders the preset rock and blocks placement onto that square', async () => {
    render(<App />);

    await screen.findByText(/10 \/ 10 units placed/i);
    const rockSquare = screen.getByRole('button', { name: /square 5,8 contains rock terrain/i });

    expect(rockSquare).toBeDisabled();
  });

  it('uses batch size 1 as a replayable single encounter run', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/10 \/ 10 units placed/i);
    await user.selectOptions(screen.getByRole('combobox', { name: /dm behavior/i }), 'balanced');
    const batchSizeInput = screen.getByRole('spinbutton', { name: /batch size/i });
    await user.clear(batchSizeInput);
    await user.type(batchSizeInput, '1');
    await user.click(screen.getByRole('button', { name: /batch run/i }));

    expect(await screen.findByText(/Replay Frame 1/i)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /combat grid/i })).toBeInTheDocument();
    expect(screen.getByText(/Per-Round Event Log/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Level 2 Fighter Sample Build/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Enemy Preset/i).length).toBeGreaterThan(0);
  });

  it('lets the user return from replay to edit the layout', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/10 \/ 10 units placed/i);
    await user.selectOptions(screen.getByRole('combobox', { name: /dm behavior/i }), 'balanced');
    const batchSizeInput = screen.getByRole('spinbutton', { name: /batch size/i });
    await user.clear(batchSizeInput);
    await user.type(batchSizeInput, '1');
    await user.click(screen.getByRole('button', { name: /batch run/i }));
    await screen.findByRole('img', { name: /combat grid/i });

    await user.click(screen.getByRole('button', { name: /edit layout/i }));

    expect(screen.getByRole('grid', { name: /placement grid/i })).toBeInTheDocument();
    expect(screen.getByText(/Selected unit:/i)).toBeInTheDocument();
    expect(screen.queryByText(/Replay Frame 1/i)).not.toBeInTheDocument();
  });

  it('shows combined DM summaries for balanced players in a batch run', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/10 \/ 10 units placed/i);
    const batchSizeInput = screen.getByRole('spinbutton', { name: /batch size/i });
    await user.clear(batchSizeInput);
    await user.type(batchSizeInput, '2');
    await user.click(screen.getByRole('button', { name: /batch run/i }));

    expect(await screen.findByText(/Batch Progress/i)).toBeInTheDocument();
    expect(screen.getByText(/Elapsed:/i)).toBeInTheDocument();
    expect((await screen.findAllByText(/Smart Player Win Rate/i)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Dumb Player Win Rate/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Player Policy/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Kind DM/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Balanced DM/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Evil DM/i).length).toBeGreaterThan(0);
  });
});
