import { useEffect, useState } from 'react';
import { fetchObservations, fetchStations, uploadCSV } from '../services/api';
import { Observation, Station, InferenceResult } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { TableSkeleton } from '../design-system/components/SkeletonLoader';

interface DataExplorerViewProps {
  selectedStationId?: string;
  onSelectStation?: (stationId: string) => void;
}

export function DataExplorerView({ selectedStationId, onSelectStation }: DataExplorerViewProps = {}) {
  const [observations, setObservations] = useState<Observation[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedStation, setSelectedStation] = useState<string>(selectedStationId || '');

  useEffect(() => {
    if (selectedStationId !== undefined) {
      setSelectedStation(selectedStationId);
    }
  }, [selectedStationId]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [isLoading, setIsLoading] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<boolean>(false);
  const [uploadSummary, setUploadSummary] = useState<{
    total_records: number;
    valid_records: number;
    anomalies_detected: number;
    processing_time_ms: number;
    results: InferenceResult[];
  } | null>(null);

  const loadObservations = async () => {
    setIsLoading(true);
    try {
      const [obsRes, stRes] = await Promise.all([
        fetchObservations({
          station_id: selectedStation || undefined,
          limit: 50,
          page: page,
        }),
        fetchStations(),
      ]);
      setObservations(obsRes.items);
      setTotalCount(obsRes.total);
      setStations(stRes.items);
    } catch (err) {
      console.error('Failed to load observations:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadObservations();
  }, [selectedStation, page]);

  const handleFileUpload = async () => {
    if (!uploadFile) return;
    setUploadProgress(true);
    try {
      const result = await uploadCSV(uploadFile);
      setUploadSummary(result);
      loadObservations();
    } catch (err: any) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      setUploadProgress(false);
    }
  };

  const downloadSampleCSV = () => {
    const csvContent =
      'timestamp,station_id,temperature,pressure,humidity\n' +
      '2026-08-24T12:00:00Z,AWS-001,24.5,1012.3,62.1\n' +
      '2026-08-24T12:05:00Z,AWS-001,24.8,1012.1,61.8\n' +
      '2026-08-24T12:10:00Z,AWS-001,58.2,1012.0,61.5\n' + // Thermal spike
      '2026-08-24T12:15:00Z,AWS-001,25.1,1011.8,60.9\n' +
      '2026-08-24T12:20:00Z,AWS-001,25.4,1011.6,60.5\n';

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'datamend_sample_aws_telemetry.csv';
    a.click();
  };

  return (
    <div className="space-y-6">
      {/* Upload & Ingestion Section */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-2 font-mono">
              
              Batch Dataset Ingestion & Validation Dropzone
            </h3>
            <p className="text-xs text-slate-600 mt-0.5">
              Upload historical AWS CSV records (`timestamp`, `temperature`, `pressure`, `humidity`) for 5-tier batch inference
            </p>
          </div>

          <button
            onClick={downloadSampleCSV}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#F4F6FA] hover:bg-[#EDF1F7] text-slate-700 rounded-lg text-xs font-mono font-medium border border-[#D3DCE7] transition-all shadow-sm"
          >
             Sample CSV Template
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-3 p-4 bg-[#F4F6FA] border border-[#D3DCE7]/70 rounded-xl">
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setUploadFile(e.target.files ? e.target.files[0] : null)}
            className="text-xs text-slate-600 font-mono file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-sky-500/15 file:text-sky-700 hover:file:bg-sky-500/25 cursor-pointer"
          />

          <button
            onClick={handleFileUpload}
            disabled={!uploadFile || uploadProgress}
            className="flex items-center gap-2 px-4 py-2 bg-sky-500 hover:bg-sky-400 disabled:bg-slate-300 text-slate-950 disabled:text-slate-500 font-mono font-bold text-xs rounded-lg transition-all shadow"
          >
            {uploadProgress ? (
              <>
                 Ingesting & Running Batch ML...
              </>
            ) : (
              <>
                 Execute 5-Tier ML Batch Inference
              </>
            )}
          </button>
        </div>

        {uploadSummary && (
          <div className="p-4 bg-[#F4F6FA] border border-emerald-500/40 rounded-xl text-xs grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
            <div>
              <span className="text-slate-500 block text-[10px] uppercase">TOTAL RECORDS</span>
              <span className="text-base font-bold text-slate-900">{uploadSummary.total_records}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px] uppercase">VALID QC PASS</span>
              <span className="text-base font-bold text-emerald-600">{uploadSummary.valid_records}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px] uppercase">ANOMALIES FLAGGED</span>
              <span className="text-base font-bold text-rose-600">{uploadSummary.anomalies_detected}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px] uppercase">PROCESSING TIME</span>
              <span className="text-base font-bold text-sky-600">{uploadSummary.processing_time_ms.toFixed(1)} ms</span>
            </div>
          </div>
        )}
      </div>

      {/* Persisted Historical Telemetry Table */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">
              Persisted Telemetry Store ({totalCount.toLocaleString()} Records)
            </h3>
          </div>

          <div className="flex items-center gap-3 font-mono">
            <select
              value={selectedStation}
              onChange={(e) => {
                setSelectedStation(e.target.value);
                setPage(1);
                if (onSelectStation && e.target.value) {
                  onSelectStation(e.target.value);
                }
              }}
              className="bg-[#F4F6FA] border border-[#D3DCE7] text-slate-700 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-bold"
            >
              <option value="">All Weather Stations</option>
              {stations.map((s) => (
                <option key={s.station_id} value={s.station_id}>
                  {s.station_id}
                </option>
              ))}
            </select>

          <button
            onClick={loadObservations}
            className="px-2.5 py-1.5 bg-[#F4F6FA] hover:bg-[#EDF1F7] text-slate-700 rounded-lg text-xs border border-[#D3DCE7] font-mono font-semibold"
          >
            Reload
          </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 font-sans font-semibold uppercase text-[11px] tracking-wider">
                <th className="pb-3">ID</th>
                <th className="pb-3">Timestamp (UTC)</th>
                <th className="pb-3">Station</th>
                <th className="pb-3">Temperature (°C)</th>
                <th className="pb-3">Pressure (hPa)</th>
                <th className="pb-3">Humidity (%)</th>
                <th className="pb-3 text-right">QC Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-6">
                    <TableSkeleton rows={8} />
                  </td>
                </tr>
              ) : observations.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500 font-sans">
                    No telemetry records found.
                  </td>
                </tr>
              ) : (
                observations.map((obs) => (
                  <tr key={obs.id || Math.random()} className="hover:bg-[#EDF1F7] transition-colors">
                    <td className="py-2.5 text-slate-500">#{obs.id}</td>
                    <td className="py-2.5 text-slate-600">
                      {new Date(obs.timestamp).toLocaleString()}
                    </td>
                    <td className="py-2.5 text-sky-600 font-bold">{obs.station_id}</td>
                    <td className="py-2.5 text-slate-900 font-bold">
                      {obs.temperature !== undefined ? obs.temperature.toFixed(2) : '--'}
                    </td>
                    <td className="py-2.5 text-slate-700">
                      {obs.pressure !== undefined ? obs.pressure.toFixed(1) : '--'}
                    </td>
                    <td className="py-2.5 text-slate-700">
                      {obs.humidity !== undefined ? obs.humidity.toFixed(1) : '--'}
                    </td>
                    <td className="py-2.5 text-right">
                      <StatusBadge
                        label={obs.validation_status || 'VALID'}
                        variant="nominal"
                        size="sm"
                      />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        <div className="pt-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500 font-mono">
          <span>Page {page} of {Math.max(1, Math.ceil(totalCount / 50))}</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 bg-[#F4F6FA] hover:bg-[#EDF1F7] disabled:opacity-40 rounded text-xs text-slate-700 border border-[#D3DCE7]"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= Math.ceil(totalCount / 50)}
              className="px-3 py-1 bg-[#F4F6FA] hover:bg-[#EDF1F7] disabled:opacity-40 rounded text-xs text-slate-700 border border-[#D3DCE7]"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
