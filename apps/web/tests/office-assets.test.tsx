import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OfficeRoom } from '@/features/office/OfficeRoom';
import { DeskSprite } from '@/features/office/DeskSprite';
import { roles } from '@/features/office/projections';

describe('authored office sprite layers', () => {
  it('keeps the room separate from the three workstations', () => {
    const { container } = render(<OfficeRoom />);
    expect(
      container.querySelector('[data-room-system="authored-sprites"]'),
    ).toBeInTheDocument();
    expect(
      container.querySelectorAll('[data-room-object="plant"]'),
    ).toHaveLength(2);
    expect(container.querySelector('[data-character]')).toBeNull();
  });
  it.each(roles)(
    '%s composes transparent furniture, character, and role props',
    (kind) => {
      const { container } = render(<DeskSprite kind={kind} />);
      expect(
        container.querySelector(`[data-desk-sprite="${kind}"]`),
      ).toBeInTheDocument();
      expect(
        container.querySelector(`[data-character="${kind}"]`),
      ).toHaveAttribute('data-sprite-state', 'idle');
      expect(
        container.querySelector('[data-desk-object="chair"]'),
      ).toBeInTheDocument();
      expect(
        container.querySelector('[data-desk-object="desk"]'),
      ).toBeInTheDocument();
      expect(container.querySelector('.sprite-equipment')).toBeInTheDocument();
      expect(container.querySelector('svg')).toBeNull();
    },
  );
  it('selects a character presentation state from projected work and receipt state', () => {
    const { container, rerender } = render(
      <DeskSprite kind="developer" status="Working" active />,
    );
    expect(
      container.querySelector('[data-character="developer"]'),
    ).toHaveAttribute('data-sprite-state', 'working');
    rerender(<DeskSprite kind="developer" status="Blocked" />);
    expect(
      container.querySelector('[data-character="developer"]'),
    ).toHaveAttribute('data-sprite-state', 'blocked');
    rerender(<DeskSprite kind="developer" status="Working" active received />);
    expect(
      container.querySelector('[data-character="developer"]'),
    ).toHaveAttribute('data-sprite-state', 'acknowledging');
  });
});
