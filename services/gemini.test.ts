import { describe, expect, it, vi } from 'vitest';

import { getApiBaseUrl, getAuthHeaders, urlToBlob } from './gemini';

describe('services/gemini', () => {
  it('getApiBaseUrl prefers VITE_API_BASE_URL', () => {
    const meta = import.meta as any;
    const original = meta.env?.VITE_API_BASE_URL;
    meta.env = meta.env || {};
    meta.env.VITE_API_BASE_URL = '/api/';
    expect(getApiBaseUrl()).toBe('/api');
    meta.env.VITE_API_BASE_URL = original;
  });

  it('getAuthHeaders reads token from localStorage', () => {
    localStorage.setItem('LUMINA_API_TOKEN', 't');
    expect(getAuthHeaders()).toEqual({ Authorization: 'Bearer t' });
    localStorage.removeItem('LUMINA_API_TOKEN');
    expect(getAuthHeaders()).toEqual({});
  });

  it('urlToBlob sends auth headers when fetching', async () => {
    localStorage.setItem('LUMINA_API_TOKEN', 't');
    const fetchMock = vi.fn(async () => new Response(new Blob(['x'])));
    (globalThis as any).fetch = fetchMock;

    await urlToBlob('https://example.com/x.png');

    expect(fetchMock).toHaveBeenCalled();
    const call = fetchMock.mock.calls[0];
    const opts = call[1] as RequestInit;
    expect((opts.headers as any).Authorization).toBe('Bearer t');
  });
});

