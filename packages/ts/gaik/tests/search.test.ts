import { describe, expect, it } from 'vitest';
import { cosineSimilarity, reciprocalRankFusion, rerank } from '../src/search/index.js';

describe('cosineSimilarity', () => {
  it('should return 1 for identical vectors', () => {
    const vector = [1, 2, 3, 4, 5];
    expect(cosineSimilarity(vector, vector)).toBeCloseTo(1, 5);
  });

  it('should return 0 for orthogonal vectors', () => {
    expect(cosineSimilarity([1, 0, 0], [0, 1, 0])).toBeCloseTo(0, 5);
  });

  it('should return -1 for opposite vectors', () => {
    expect(cosineSimilarity([1, 2, 3], [-1, -2, -3])).toBeCloseTo(-1, 5);
  });

  it('should throw for vectors of different lengths', () => {
    expect(() => cosineSimilarity([1, 2, 3], [1, 2])).toThrow('same length');
  });

  it('should return 0 for zero vectors', () => {
    expect(cosineSimilarity([0, 0, 0], [1, 2, 3])).toBe(0);
  });
});

describe('reciprocalRankFusion', () => {
  it('should combine multiple ranked lists', () => {
    const scores = reciprocalRankFusion([
      ['a', 'b', 'c'],
      ['b', 'a', 'd'],
    ]);

    expect(scores.has('a')).toBe(true);
    expect(scores.has('b')).toBe(true);
    expect(scores.has('d')).toBe(true);
  });

  it('should give higher scores to items ranked highly in multiple lists', () => {
    const scores = reciprocalRankFusion([
      ['a', 'b', 'c'],
      ['a', 'c', 'b'],
      ['a', 'b', 'c'],
    ]);

    expect(scores.get('a')).toBeGreaterThan(scores.get('b')!);
  });

  it('should use k parameter correctly', () => {
    const scores = reciprocalRankFusion([['a']], 60);
    expect(scores.get('a')).toBeCloseTo(1 / 61, 10);
  });

  it('should handle empty lists', () => {
    expect(reciprocalRankFusion([]).size).toBe(0);
  });
});

describe('rerank', () => {
  it('should rerank results by custom score function', () => {
    const results = [
      { id: '1', content: 'short' },
      { id: '2', content: 'this is longer content' },
    ];

    const reranked = rerank(results, (item) => item.content.length);

    expect(reranked[0].id).toBe('2');
    expect(reranked[0].rerankedScore).toBeGreaterThan(reranked[1].rerankedScore);
  });

  it('should preserve original data while adding rerankedScore', () => {
    const results = [{ id: '1', content: 'test' }];
    const reranked = rerank(results, () => 1);

    expect(reranked[0].id).toBe('1');
    expect(reranked[0].content).toBe('test');
    expect(reranked[0].rerankedScore).toBe(1);
  });
});
