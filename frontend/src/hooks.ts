import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { Game, Strategy } from "./api/types";

let gamesCache: Game[] | null = null;
let stratCache: Strategy[] | null = null;

export function useGames() {
  const [games, setGames] = useState<Game[]>(gamesCache || []);
  useEffect(() => {
    if (gamesCache) return;
    api.get<Game[]>("/draws/games").then((g) => {
      gamesCache = g;
      setGames(g);
    });
  }, []);
  return games;
}

export function useStrategies() {
  const [strategies, setStrategies] = useState<Strategy[]>(stratCache || []);
  useEffect(() => {
    if (stratCache) return;
    api.get<Strategy[]>("/predictions/strategies").then((s) => {
      stratCache = s;
      setStrategies(s);
    });
  }, []);
  return strategies;
}

export function gameLabel(games: Game[], key: string) {
  return games.find((g) => g.key === key)?.label || key;
}
