'use client';

import React, { useState, useMemo } from 'react';
import { Download, Search, AlertTriangle, FileSpreadsheet, FileJson } from 'lucide-react';
import { AnomalyItem } from '@/types/api';
import { Panel, Button, Chip } from '@/shared/ui';

interface AnomaliesTableProps {
  anomalies: AnomalyItem[];
}

export const AnomaliesTable: React.FC<AnomaliesTableProps> = ({ anomalies }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const filtered = useMemo(() => {
    return anomalies.filter((a) => {
      const col = (a.columnName || a.column || '').toLowerCase();
      const time = (a.timestamp || '').toLowerCase();
      const matchSearch = col.includes(searchTerm.toLowerCase()) || time.includes(searchTerm.toLowerCase());
      const matchSeverity = severityFilter === 'ALL' || a.severity === severityFilter;
      return matchSearch && matchSeverity;
    });
  }, [anomalies, searchTerm, severityFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);

  const handleExportJson = () => {
    if (anomalies.length === 0) return;
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(anomalies, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `datamend-anomalies-${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleExportCsv = () => {
    if (anomalies.length === 0) return;
    const headers = ['Timestamp', 'Signal Channel', 'Observed Value', 'Anomaly Score', 'Severity'];
    const rows = anomalies.map((a) => [
      a.timestamp ?? '',
      a.columnName || a.column || '',
      a.value !== undefined ? a.value : '',
      a.score !== undefined ? a.score : '',
      a.severity ?? '',
    ]);
    const csvContent =
      'data:text/csv;charset=utf-8,' +
      [headers.join(','), ...rows.map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))].join('\n');
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', encodeURI(csvContent));
    downloadAnchor.setAttribute('download', `datamend-anomalies-${Date.now()}.csv`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <Panel
      title={`Detected Anomaly Incidents (${anomalies.length})`}
      subtitle="Log of sequence timestamps exceeding detection threshold"
      icon={<AlertTriangle size={16} />}
      headerActions={
        <div className="flex items-center gap-1.5">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleExportCsv}
            disabled={anomalies.length === 0}
            icon={<FileSpreadsheet size={12} />}
          >
            Export CSV
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleExportJson}
            disabled={anomalies.length === 0}
            icon={<FileJson size={12} />}
          >
            Export JSON
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        {/* Filters */}
        <div className="flex flex-wrap gap-2 items-center justify-between">
          <div className="relative flex-1 min-w-[200px]">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              className="form-input pl-7 text-xs"
              placeholder="Filter by timestamp or channel..."
              value={searchTerm}
              disabled={anomalies.length === 0}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setPage(1);
              }}
            />
          </div>

          <div className="flex gap-1">
            {['ALL', 'HIGH', 'MEDIUM', 'LOW'].map((sev) => {
              const isSelected = severityFilter === sev;
              return (
                <button
                  key={sev}
                  type="button"
                  disabled={anomalies.length === 0}
                  onClick={() => {
                    setSeverityFilter(sev);
                    setPage(1);
                  }}
                  className={`px-2 py-1 rounded text-[11px] font-bold border transition-colors ${
                    isSelected
                      ? 'bg-panel-header text-white border-panel-header'
                      : 'bg-white text-slate-600 border-border hover:bg-slate-50'
                  } ${anomalies.length === 0 ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  {sev}
                </button>
              );
            })}
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto border border-border rounded">
          <table className="data-table" aria-label="Detected Anomaly Incidents Table">
            <thead>
              <tr>
                <th scope="col">Timestamp</th>
                <th scope="col">Signal Channel</th>
                <th scope="col">Observed Value</th>
                <th scope="col">Score</th>
                <th scope="col">Severity</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-slate-500">
                    <div className="flex flex-col items-center justify-center gap-1.5 py-4">
                      <AlertTriangle size={24} className="text-slate-300 mb-1" />
                      <span className="text-xs font-semibold text-slate-600">
                        {anomalies.length === 0
                          ? 'No anomaly incidents detected yet'
                          : 'No incidents match your filter'}
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {anomalies.length === 0
                          ? "Load scores and click '2. Run Anomaly Detection' to detect anomalies."
                          : 'Try adjusting your search query or severity filter.'}
                      </span>
                    </div>
                  </td>
                </tr>
              ) : (
                pageItems.map((item, idx) => {
                  const col = item.columnName || item.column || '—';
                  return (
                    <tr key={idx}>
                      <td className="tabular-nums text-slate-600">{item.timestamp}</td>
                      <td className="font-bold text-panel-header">{col}</td>
                      <td className="tabular-nums">
                        {typeof item.value === 'number' ? item.value.toFixed(3) : '—'}
                      </td>
                      <td className="tabular-nums font-bold text-status-critical">
                        {typeof item.score === 'number' ? item.score.toFixed(4) : '—'}
                      </td>
                      <td>
                        <Chip variant={item.severity}>{item.severity}</Chip>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between pt-1">
            <span className="text-xs text-slate-500">
              Page {page} of {totalPages} ({filtered.length} total entries)
            </span>
            <div className="flex gap-1">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
};
