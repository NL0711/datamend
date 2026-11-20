import { describe, expect, it } from 'vitest';
import { detectProvider, looksLikeKaggleToken, providerLabel } from './importLink';

describe('detectProvider', () => {
  it('recognises Kaggle dataset links, owner/name and notebook references', () => {
    expect(detectProvider('https://www.kaggle.com/datasets/nathashalewis/majorproj-rainfall')).toBe('kaggle');
    expect(detectProvider('nathashalewis/majorproj-rainfall')).toBe('kaggle');
    expect(detectProvider('  owner/data.set_1  ')).toBe('kaggle');
    expect(detectProvider('kernel:owner/my-notebook')).toBe('kaggle');
    expect(detectProvider('https://www.kaggle.com/code/owner/nb')).toBe('kaggle');
  });
  it('recognises S3 links in every form', () => {
    expect(detectProvider('s3://my-bucket/rain/file.csv')).toBe('aws');
    expect(detectProvider('https://my-bucket.s3.ap-south-1.amazonaws.com/file.csv')).toBe('aws');
    expect(detectProvider('https://s3.eu-west-1.amazonaws.com/bucket/key')).toBe('aws');
  });
  it('gives null for anything else, so the Import button stays off', () => {
    for (const bad of ['', '   ', 'hello', 'a/b/c', 'https://example.com/x', 'https://evilkaggle.com/datasets/a/b', 'https://kaggle.com.evil.example/a/b', 'http://[bad', 'owner/']) {
      expect(detectProvider(bad)).toBeNull();
    }
  });
  it('labels the source', () => {
    expect(providerLabel('kaggle')).toBe('Kaggle'); expect(providerLabel('aws')).toBe('Amazon S3'); expect(providerLabel(null)).toBe('');
  });
});

describe('looksLikeKaggleToken', () => {
  it('accepts a KGAT token and refuses spaces, short and long values', () => {
    expect(looksLikeKaggleToken('KGAT_abcdef0123456789')).toBe(true);
    expect(looksLikeKaggleToken(' KGAT_abcdef0123456789 ')).toBe(true);
    for (const bad of ['', 'short', 'has space in it', 'x'.repeat(300), 'semi;colon;123456']) expect(looksLikeKaggleToken(bad)).toBe(false);
  });
});
