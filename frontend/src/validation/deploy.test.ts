// The dashboard calls relative /api/... paths (the Vite dev server proxies them to the backend). On Vercel there is no dev proxy, so
// frontend/vercel.json must forward /api to the backend, or every call returns 404. These tests keep that rewrite from being lost again.
import { describe, expect, it } from 'vitest';
import vercelConfig from '../../vercel.json';

type Rewrite = { source: string; destination: string };
const config = vercelConfig as { rewrites: Rewrite[]; outputDirectory: string };

describe('vercel.json', () => {
  it('forwards /api to the backend over https, keeping the path', () => {
    const api = config.rewrites.find((r) => r.source.startsWith('/api/'));
    expect(api).toBeDefined();
    expect(api!.source).toBe('/api/:path*');
    expect(api!.destination).toMatch(/^https:\/\/[^/]+\/api\/:path\*$/);
  });
  it('lists the API rewrite before the single-page fallback, so /api is never answered with index.html', () => {
    const idx = config.rewrites.findIndex((r) => r.source.startsWith('/api/'));
    const spa = config.rewrites.findIndex((r) => r.destination === '/index.html');
    expect(idx).toBeGreaterThanOrEqual(0);
    expect(spa).toBeGreaterThan(idx);
  });
  it('serves the Vite build output', () => {
    expect(config.outputDirectory).toBe('dist');
  });
});
