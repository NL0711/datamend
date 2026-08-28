'use client';

import React, { useState, useMemo } from 'react';
import { Download, Search, AlertTriangle, FileSpreadsheet, FileJson } from 'lucide-react';
import { AnomalyItem } from '@/types/api';

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
    <div className="panel">
      {/* Edge-to-edge Header Bar */}
      <div className="panel-header">
        <div>
          <div className="panel-header-title">
            <span>Detected Anomaly Incidents ({anomalies.length})</span>
          </div>
          <div className="panel-header-subtitle">
            Log of sequence timestamps exceeding detection threshold
          </div>
        </div>

        <div style={{ display: 'flex', gap: 6 }}>
          <button
            type="button"
            onClick={handleExportCsv}
            disabled={anomalies.length === 0}
            className="btn btn-secondary"
            style={{ padding: '4px 10px', fontSize: '0.6875rem' }}
          >
            <FileSpreadsheet size={12} /> Export CSV
          </button>
          <button
            type="button"
            onClick={handleExportJson}
            disabled={anomalies.length === 0}
            className="btn btn-secondary"
            style={{ padding: '4px 10px', fontSize: '0.6875rem' }}
          >
            <FileJson size={12} /> Export JSON
          </button>
        </div>
      </div>

      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Filters */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
            <Search
              size={13}
              style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
            />
            <input
              type="text"
              className="form-input"
              placeholder="Filter by timestamp or channel..."
              value={searchTerm}
              disabled={anomalies.length === 0}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setPage(1);
              }}
              style={{ paddingLeft: 28, fontSize: '0.8125rem' }}
            />
          </div>

          <div style={{ display: 'flex', gap: 4 }}>
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
                  style={{
                    backgroundColor: isSelected ? '#1c4b5a' : '#ffffff',
                    border: `1px solid ${isSelected ? '#1c4b5a' : 'var(--border)'}`,
                    color: isSelected ? '#ffffff' : 'var(--text-secondary)',
                    borderRadius: 3,
                    padding: '4px 8px',
                    fontSize: '0.6875rem',
                    fontWeight: 700,
                    cursor: anomalies.length === 0 ? 'not-allowed' : 'pointer',
                    opacity: anomalies.length === 0 ? 0.5 : 1,
                  }}
                >
                  {sev}
                </button>
              );
            })}
          </div>
        </div>

        {/* Table */}
        <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 4 }}>
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
                  <td colSpan={5} style={{ textAlign: 'center', padding: '32px 16px', color: '#64748b' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                      <AlertTriangle size={24} style={{ color: '#94a3b8', opacity: 0.7 }} />
                      <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#475569' }}>
                        {anomalies.length === 0
                          ? 'No anomaly incidents detected yet'
                          : 'No incidents match your filter'}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
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
                      <td className="tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                        {item.timestamp}
                      </td>
                      <td style={{ fontWeight: 700, color: '#1c4b5a' }}>
                        {col}
                      </td>
                      <td className="tabular-nums">
                        {typeof item.value === 'number' ? item.value.toFixed(3) : '—'}
                      </td>
                      <td className="tabular-nums" style={{ color: '#d32f2f', fontWeight: 700 }}>
                        {typeof item.score === 'number' ? item.score.toFixed(4) : '—'}
                      </td>
                      <td>
                        <span
                          className={`chip ${
                            item.severity === 'HIGH'
                              ? 'chip-critical'
                              : item.severity === 'MEDIUM'
                              ? 'chip-warning'
                              : 'chip-info'
                          }`}
                        >
                          {item.severity}
                        </span>
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
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 2 }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Page {page} of {totalPages} ({filtered.length} total entries)
            </span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                style={{ padding: '3px 8px', fontSize: '0.6875rem' }}
              >
                Previous
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                style={{ padding: '3px 8px', fontSize: '0.6875rem' }}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
