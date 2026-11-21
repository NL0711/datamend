import { describe, expect, it } from 'vitest';
import { clockUtc, fmtLat, fmtLatLon, fmtLon, packetCount, streamStatsLine } from './geo';
import { emptyRunText } from '../components/StationRunPanel';
import { agentErrorText } from '../components/agentText';
import { simulatorLine } from '../components/SimulatorControls';
import { ServiceError } from './api';

describe('geo and display helpers', () => {
  it('puts the hemisphere letter from the sign, never a negative number with E', () => {
    expect(fmtLon(-97.28)).toBe('97.28°W');
    expect(fmtLon(73.8)).toBe('73.80°E');
    expect(fmtLat(-12.5)).toBe('12.50°S');
    expect(fmtLatLon(18.5, -97.28, 4)).toBe('18.5000°N, 97.2800°W');
  });
  it('formats a UTC clock regardless of the local zone', () => {
    expect(clockUtc(new Date('2026-11-21T14:03:09Z'))).toBe('14:03:09');
    expect(clockUtc(new Date('nope'))).toBe('');
  });
  it('takes the packet count from the data-sources status only', () => {
    expect(packetCount({ packet_count: 120 })).toBe(120);
    expect(packetCount(null)).toBeNull();
  });
  it('summarises stream statistics and passes an error through', () => {
    expect(streamStatsLine({ total_anomalies: 3, sensor_faults: 2, meteorological_extremes: 1 }, null)).toBe('3 detections (2 sensor faults, 1 meteorological extreme).');
    expect(streamStatsLine(null, 'not available on this server')).toBe('not available on this server');
    expect(streamStatsLine(null, null)).toMatch(/loading/);
  });
  it('does not imply a station is empty when it has no file run', () => {
    expect(emptyRunText('flagged')).toMatch(/imported files only/);
    expect(emptyRunText('flagged')).toMatch(/live stream/);
  });
  it('explains an absent agent service instead of showing a raw 404', () => {
    expect(agentErrorText(new ServiceError(404, '404: Not Found', 'Not Found'))).toMatch(/Agent service not available on this server/);
    expect(agentErrorText(new ServiceError(500, 'boom', 'boom'))).toMatch(/boom/);
  });
  it('shows the simulator state without any start or stop wording', () => {
    const line = simulatorLine({ running: true, interval_seconds: 5, active_stations: ['A', 'B'], step_count: 7, pending_injections_count: 0 });
    expect(line).toBe('running · every 5 s · step 7 · 0 fault(s) queued · 2 stations');
  });
});
