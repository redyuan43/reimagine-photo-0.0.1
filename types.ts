
export interface PlanItem {
  id: string;
  problem: string;
  solution: string;
  engine: string;
  category?: string;
  type: 'generative' | 'adjustment';
  checked: boolean;
  isCustom?: boolean;
  selectedOption?: string;
  options?: string[];
  priority?: 'high' | 'medium' | 'low';
  isOption?: boolean;
}

export interface AnalysisResponse {
  analysis: {
    id: string;
    problem: string;
    solution: string;
    engine: string;
    type: 'generative' | 'adjustment';
    options?: string[];
  }[];
}

declare global {
  interface AIStudio {
    hasSelectedApiKey: () => Promise<boolean>;
    openSelectKey: () => Promise<void>;
  }

  interface Window {
    aistudio?: AIStudio;
  }
}
