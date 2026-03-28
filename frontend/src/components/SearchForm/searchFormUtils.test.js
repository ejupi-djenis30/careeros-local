import { describe, it, expect } from 'vitest';
import { mergeRoleDescription, normalizePrefillProfile } from './searchFormUtils';

describe('searchFormUtils', () => {
  // ── mergeRoleDescription ───────────────────────────────────────────────────

  describe('mergeRoleDescription', () => {
    it('returns baseDescription when extraRequirements is empty', () => {
      expect(mergeRoleDescription('Senior dev', '')).toBe('Senior dev');
    });

    it('returns extraRequirements when baseDescription is empty', () => {
      expect(mergeRoleDescription('', 'React experience')).toBe('React experience');
    });

    it('returns empty string when both are empty', () => {
      expect(mergeRoleDescription('', '')).toBe('');
    });

    it('returns baseDescription when it already contains extraRequirements', () => {
      const base = 'Senior dev with React experience';
      const extra = 'React experience';
      expect(mergeRoleDescription(base, extra)).toBe(base);
    });

    it('merges with separator when both are distinct', () => {
      const result = mergeRoleDescription('Senior dev', 'Python required');
      expect(result).toContain('Senior dev');
      expect(result).toContain('Python required');
      expect(result).toContain('Additional search requirements');
    });

    it('handles null/undefined gracefully', () => {
      expect(mergeRoleDescription(null, null)).toBe('');
      expect(mergeRoleDescription(undefined, undefined)).toBe('');
    });

    it('handles numeric values by coercing to string', () => {
      const result = mergeRoleDescription('Dev', 0);
      expect(result).toBe('Dev');
    });
  });

  // ── normalizePrefillProfile ────────────────────────────────────────────────

  describe('normalizePrefillProfile', () => {
    it('returns null for null input', () => {
      expect(normalizePrefillProfile(null)).toBeNull();
    });

    it('returns null for undefined input', () => {
      expect(normalizePrefillProfile(undefined)).toBeNull();
    });

    it('removes deprecated fields', () => {
      const profile = {
        id: 1,
        name: 'My profile',
        role_description: 'Developer',
        search_strategy: 'Focus on Python',
        preferred_domains: ['it'],
        workload_min: 80,
        workload_max: 100,
        hard_max_distance_km: 50,
      };
      const result = normalizePrefillProfile(profile);
      expect(result).not.toHaveProperty('search_strategy');
      expect(result).not.toHaveProperty('preferred_domains');
      expect(result).not.toHaveProperty('workload_min');
      expect(result).not.toHaveProperty('workload_max');
      expect(result).not.toHaveProperty('hard_max_distance_km');
    });

    it('preserves non-deprecated fields', () => {
      const profile = { id: 1, name: 'Test', role_description: 'Dev', location: 'Zurich' };
      const result = normalizePrefillProfile(profile);
      expect(result.id).toBe(1);
      expect(result.name).toBe('Test');
      expect(result.location).toBe('Zurich');
    });

    it('merges search_strategy into role_description', () => {
      const profile = {
        role_description: 'Backend developer',
        search_strategy: 'Python and FastAPI',
      };
      const result = normalizePrefillProfile(profile);
      expect(result.role_description).toContain('Backend developer');
      expect(result.role_description).toContain('Python and FastAPI');
    });

    it('uses search_strategy as role_description when role_description is absent', () => {
      const profile = { name: 'Test', search_strategy: 'Python only' };
      const result = normalizePrefillProfile(profile);
      expect(result.role_description).toBe('Python only');
    });

    it('returns empty object properties from profile without deprecated fields', () => {
      const profile = { id: 5, name: 'Simple' };
      const result = normalizePrefillProfile(profile);
      expect(result.id).toBe(5);
      expect(result.name).toBe('Simple');
    });
  });
});
