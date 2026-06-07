const KEY = "melateai_default_game";
const VALID = ["melate", "revancha", "melate_retro", "revanchita"];

export function getDefaultGame(): string {
  const v = localStorage.getItem(KEY);
  return v && VALID.includes(v) ? v : "melate";
}

export function setDefaultGame(game: string) {
  if (VALID.includes(game)) localStorage.setItem(KEY, game);
}
