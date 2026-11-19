import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ADMIN_TOKEN_KEY } from './api';
import { adminEmail, signIn, signOut } from './Login';

const store = new Map<string, string>();
let fetchMock: ReturnType<typeof vi.fn>;
const reply = (body: unknown, status = 200) => ({ ok: status < 300, status, json: async () => body }) as unknown as Response;

beforeEach(() => {
  store.clear();
  vi.stubGlobal('sessionStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v); },
    removeItem: (k: string) => { store.delete(k); },
  });
  vi.stubGlobal('window', { location: { hash: '' } });
  fetchMock = vi.fn(async () => reply({ token: 'T', email: 'a@b.in', expires_in: 60 }));
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => { vi.unstubAllGlobals(); });

describe('sign in and out', () => {
  it('signIn posts the credentials and stores the token and email', async () => {
    await signIn('a@b.in', 'pw');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/auth/login');
    expect(JSON.parse(init.body as string)).toEqual({ email: 'a@b.in', password: 'pw' });
    expect(store.get(ADMIN_TOKEN_KEY)).toBe('T');
    expect(adminEmail()).toBe('a@b.in');
  });
  it('a refused sign-in stores nothing', async () => {
    fetchMock.mockResolvedValueOnce(reply({ detail: 'wrong email or password' }, 401));
    await expect(signIn('a@b.in', 'bad')).rejects.toMatchObject({ message: 'wrong email or password' });
    expect(store.get(ADMIN_TOKEN_KEY)).toBeUndefined();
    expect(adminEmail()).toBe('');
  });
  it('signOut clears the session and tells the server', async () => {
    await signIn('a@b.in', 'pw');
    fetchMock.mockClear();
    await signOut();
    expect(store.get(ADMIN_TOKEN_KEY)).toBe('');
    expect(adminEmail()).toBe('');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/auth/logout');
    expect((init.headers as Record<string, string>)['X-Admin-Token']).toBe('T');
  });
  it('signOut while signed out makes no request, and a failing logout is swallowed', async () => {
    await signOut();
    expect(fetchMock).not.toHaveBeenCalled();
    await signIn('a@b.in', 'pw');
    fetchMock.mockRejectedValueOnce(new Error('offline'));
    await expect(signOut()).resolves.toBeUndefined();
    expect(store.get(ADMIN_TOKEN_KEY)).toBe('');
  });
});
