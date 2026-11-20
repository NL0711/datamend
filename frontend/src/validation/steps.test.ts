import { describe, expect, it } from 'vitest';
import { NO_FACTS, STEPS, doneSteps, nextStep, stepFromHash, stepHash, stepNumber } from './steps';

describe('the seven steps', () => {
  it('are in the workflow order with plain names', () => {
    expect(STEPS.map((s) => s.label)).toEqual(['Import', 'Explore & clean', 'Stations', 'Validate', 'Review', 'Anomalies', 'Models']);
    expect(stepNumber('import')).toBe(1); expect(stepNumber('models')).toBe(7);
  });
  it('chains Next buttons and ends after Models', () => {
    expect(nextStep('import')?.id).toBe('explore');
    expect(nextStep('validate')?.label).toBe('Review');
    expect(nextStep('models')).toBeNull();
  });
});

describe('which steps are done', () => {
  it('none without data', () => {
    expect(Object.values(doneSteps(NO_FACTS)).some(Boolean)).toBe(false);
  });
  it('import is done by a finished job, not by a queued one', () => {
    expect(doneSteps({ ...NO_FACTS, jobsDone: 1 }).import).toBe(true);
    expect(doneSteps({ ...NO_FACTS, jobsDone: 0 }).import).toBe(false);
  });
  it('stations need located stations, validate needs a run, review needs a decision', () => {
    const d = doneSteps({ ...NO_FACTS, locatedStations: 3, jobsChecked: 1, reviewedRows: 2, explored: true });
    expect(d).toMatchObject({ explore: true, stations: true, validate: true, review: true, anomalies: false, models: false });
  });
  it('anomalies need a run and the page opened; models need a snapshot or a model', () => {
    expect(doneSteps({ ...NO_FACTS, anomaliesOpened: true }).anomalies).toBe(false);
    expect(doneSteps({ ...NO_FACTS, anomaliesOpened: true, jobsChecked: 1 }).anomalies).toBe(true);
    expect(doneSteps({ ...NO_FACTS, snapshots: 1 }).models).toBe(true);
    expect(doneSteps({ ...NO_FACTS, models: 1 }).models).toBe(true);
  });
});

describe('step hashes', () => {
  it('#/app opens step 1 and each step has its own hash', () => {
    expect(stepFromHash('#/app')).toBe('import');
    expect(stepFromHash('#/app/explore')).toBe('explore');
    expect(stepFromHash('#/app/nonsense')).toBe('import');
    for (const s of STEPS) expect(stepFromHash(stepHash(s.id))).toBe(s.id);
    expect(stepHash('import')).toBe('#/app');
  });
});
