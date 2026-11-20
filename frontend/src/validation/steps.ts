// The seven steps of the workflow and which of them have data (pure, unit-tested in steps.test.ts). A step is done when the platform holds
// something for it, never because the user clicked past it.
export type StepId = 'import' | 'explore' | 'stations' | 'validate' | 'review' | 'anomalies' | 'models';

export const STEPS: { id: StepId; label: string; line: string }[] = [
  { id: 'import', label: 'Import', line: 'Fetch your data from an Amazon S3 link or a Kaggle dataset.' },
  { id: 'explore', label: 'Explore & clean', line: 'Look at the tables, ask the assistant, and clean the data with a policy you control.' },
  { id: 'stations', label: 'Stations', line: 'Where the stations the data identified sit on the map.' },
  { id: 'validate', label: 'Validate', line: 'Run the checks on an imported dataset and read the summary.' },
  { id: 'review', label: 'Review', line: 'Flagged rows waiting for a reviewer\'s decision.' },
  { id: 'anomalies', label: 'Anomalies', line: 'The flagged items of a run, the evidence behind each, and how they were flagged.' },
  { id: 'models', label: 'Models', line: 'Snapshots, training, the registry and gate, and how it all connects.' },
];

/** What the platform holds, gathered by the shell (counts only; nothing here is a judgement). */
export interface StepFacts {
  jobsDone: number;          // imported jobs that finished
  explored: boolean;         // a table has been loaded with rows
  locatedStations: number;   // stations the data placed on the grid
  jobsChecked: number;       // jobs that have a validation run
  reviewedRows: number;      // rows with a reviewer decision
  anomaliesOpened: boolean;  // the anomalies page was opened for a run
  snapshots: number;
  models: number;
}

export const NO_FACTS: StepFacts = { jobsDone: 0, explored: false, locatedStations: 0, jobsChecked: 0, reviewedRows: 0, anomaliesOpened: false, snapshots: 0, models: 0 };

export function doneSteps(f: StepFacts): Record<StepId, boolean> {
  return {
    import: f.jobsDone > 0,
    explore: f.explored,
    stations: f.locatedStations > 0,
    validate: f.jobsChecked > 0,
    review: f.reviewedRows > 0,
    anomalies: f.anomaliesOpened && f.jobsChecked > 0,
    models: f.snapshots > 0 || f.models > 0,
  };
}

export function nextStep(id: StepId): (typeof STEPS)[number] | null {
  const i = STEPS.findIndex((s) => s.id === id);
  return i >= 0 && i < STEPS.length - 1 ? STEPS[i + 1] : null;
}

export function stepNumber(id: StepId): number {
  return STEPS.findIndex((s) => s.id === id) + 1;
}

/** The hash a step is reachable at, so a reload keeps the page: #/app opens step 1, #/app/explore step 2, and so on. */
export function stepFromHash(hash: string): StepId {
  const m = /^#\/app\/([a-z]+)/.exec(hash);
  return STEPS.find((s) => s.id === m?.[1])?.id ?? 'import';
}
export const stepHash = (id: StepId) => (id === 'import' ? '#/app' : `#/app/${id}`);
