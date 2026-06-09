export interface User {
  id: number;
  name: string;
  email: string;
  is_admin?: boolean;
  created_at: string;
}

export interface AdminUser {
  id: number;
  name: string;
  email: string;
  is_admin: boolean;
  created_at: string;
  total_predictions: number;
  total_draws_added: number;
  evaluated_predictions: number;
  best_hits: number;
  average_hits: number;
  best_combination: {
    numbers: number[];
    game_type: string;
    strategy: string;
    hits: number;
    matched: number[];
  } | null;
  predictions?: {
    id: number;
    game_type: string;
    strategy: string;
    numbers: number[];
    score: number;
    status: string;
    used: boolean;
    best_hits: number;
    created_at: string;
  }[];
}

export interface ProfileStats {
  user: User;
  total_predictions: number;
  total_draws_added: number;
  best_hits: number;
}

export interface Game {
  key: string;
  label: string;
  max_number: number;
  pick: number;
  min_number?: number;
  kind?: "combination" | "positional";
}

export interface Strategy {
  key: string;
  label: string;
  desc: string;
}

export interface ComboFeatures {
  sum: number;
  range: number;
  mean: number;
  std: number;
  odd: number;
  even: number;
  primes: number;
  consecutive: number;
  low: number;
  mid: number;
  high: number;
  repeats_last: number;
  avg_gap: number;
  popularity: number;
}

export interface GeneratedCombo {
  numbers: number[];
  score: number;
  explanation: string;
  strategy: string;
  features: ComboFeatures;
}

export interface PredictionResult {
  hits: number;
  matched_numbers: number[];
  missed_numbers: number[];
  draw_number: number;
  draw_id: number;
  evaluated_at: string;
}

export interface Prediction {
  id: number;
  game_type: string;
  strategy: string;
  numbers: number[];
  score: number;
  explanation: string;
  status: string;
  used: boolean;
  created_at: string;
  results: PredictionResult[];
  best_hits: number;
  latest_draw_number?: number | null;
  can_evaluate?: boolean;
}

export interface Draw {
  id: number;
  game_type: string;
  draw_number: number;
  draw_date: string | null;
  numbers: number[];
  additional: number | null;
  source: string;
  created_at: string;
}

export interface DrawStats {
  game_type: string;
  label: string;
  max_number: number;
  total_draws: number;
  frequency: Record<string, number>;
  most_frequent: { number: number; count: number }[];
  least_frequent: { number: number; count: number }[];
  hot: number[];
  cold: number[];
  overdue: { number: number; gap: number }[];
  gaps: Record<string, number>;
  averages: Record<string, number>;
  sum_min: number;
  sum_max: number;
}
