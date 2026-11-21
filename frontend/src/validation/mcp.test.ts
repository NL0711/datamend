import { describe, expect, it } from 'vitest';
import { mcpEndpoint, mcpSnippets, shortTime } from './mcp';

describe('mcp helpers', () => {
  it('builds the endpoint from the page origin and tolerates a trailing slash or a path', () => {
    expect(mcpEndpoint('https://datamend.example.com')).toBe('https://datamend.example.com/api/mcp');
    expect(mcpEndpoint('http://localhost:5199/')).toBe('http://localhost:5199/api/mcp');
    expect(mcpEndpoint('http://localhost:5199/#/app')).toBe('http://localhost:5199/api/mcp');
  });

  it('writes a Claude Code command that carries the URL and the bearer header', () => {
    const s = mcpSnippets('https://d.example/api/mcp', 'dmcp_abc');
    expect(s.claudeCode).toBe('claude mcp add --transport http datamend https://d.example/api/mcp --header "Authorization: Bearer dmcp_abc"');
  });

  it('writes valid JSON for a remote HTTP client and for Claude Desktop through mcp-remote', () => {
    const s = mcpSnippets('https://d.example/api/mcp', 'dmcp_abc');
    expect(JSON.parse(s.json)).toEqual({ mcpServers: { datamend: { type: 'http', url: 'https://d.example/api/mcp', headers: { Authorization: 'Bearer dmcp_abc' } } } });
    const d = JSON.parse(s.desktop);
    expect(d.mcpServers.datamend).toEqual({ command: 'npx', args: ['-y', 'mcp-remote', 'https://d.example/api/mcp', '--header', 'Authorization:${DATAMEND_AUTH}'], env: { DATAMEND_AUTH: 'Bearer dmcp_abc' } });
  });

  it('shows a placeholder when there is no token yet, never an empty bearer', () => {
    expect(mcpSnippets('https://d.example/api/mcp', '').claudeCode).toContain('Bearer <your token>');
  });

  it('formats a timestamp and says never for a missing one', () => {
    expect(shortTime('2026-11-21T04:05:06.789+00:00')).toBe('2026-11-21 04:05');
    expect(shortTime(null)).toBe('never');
  });
});
