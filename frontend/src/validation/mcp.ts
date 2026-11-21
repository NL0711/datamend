// Helpers of the Settings page's MCP access panel (unit-tested in mcp.test.ts). No React, no network.

/** The MCP endpoint of the platform, from the address the dashboard is served on (the dev server and Vercel both forward /api to the backend). */
export function mcpEndpoint(origin: string): string {
  const o = origin.replace(/#.*$/, '').replace(/\/+$/, '');
  return `${o.replace(/(https?:\/\/[^/]+).*$/, '$1')}/api/mcp`;
}

/** Copy-paste connection snippets for an agent. With no token yet a placeholder stands in; a real token is only known right after it is made. */
export function mcpSnippets(url: string, token: string): { claudeCode: string; json: string; desktop: string } {
  const bearer = `Bearer ${token || '<your token>'}`;
  return {
    claudeCode: `claude mcp add --transport http datamend ${url} --header "Authorization: ${bearer}"`,
    json: JSON.stringify({ mcpServers: { datamend: { type: 'http', url, headers: { Authorization: bearer } } } }, null, 2),
    // Claude Desktop starts local servers, so a remote one goes through mcp-remote; the header value is passed by environment variable
    // because a space inside an argument is mangled on Windows.
    desktop: JSON.stringify({ mcpServers: { datamend: { command: 'npx', args: ['-y', 'mcp-remote', url, '--header', 'Authorization:${DATAMEND_AUTH}'], env: { DATAMEND_AUTH: bearer } } } }, null, 2),
  };
}

export function shortTime(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 16).replace('T', ' ') : 'never';
}
