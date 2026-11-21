import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import OfficeExperienceView from '@/features/office-pixel/OfficeExperienceView';

const mocks = vi.hoisted(() => ({ inspection: vi.fn() }));
vi.mock('@/lib/api/client', () => ({ getInspection: mocks.inspection, getSnapshot: vi.fn() }));
vi.mock('@/features/office-pixel/pixel/PixelOffice.jsx', () => ({
  default: ({ onSelect }: { onSelect: (kind: string) => void }) =>
    <button onClick={() => onSelect('developer')}>Select Developer in office</button>,
}));
vi.mock('@/features/office-pixel/layout/useDisplay.js', () => ({
  useDisplay: () => ({ containerRef: { current: null }, mode: 'large', inspectorWidth: 360,
    fullscreen: false, canFullscreen: false, toggleFullscreen: vi.fn() }),
}));

const agent = (kind: string) => ({
  agentId: kind, source: 'backend', name: kind[0].toUpperCase() + kind.slice(1),
  role: 'Agent', status: 'idle', mode: 'historical', currentTask: 'task-1',
  currentAction: null, model: 'fixture-model', trace: kind === 'developer' ? [{
    id: 'evt-42', at: '2026-11-21T00:00:00Z', type: 'tool', text: 'Tool request: read',
    severity: 'info', refs: { sequence: 42, run_id: 'run' },
  }] : [], tools: kind === 'developer' ? [{ id: 'op-1', tool: 'READ', input: 'greeting.txt', at: '14:01',
    durationMs: 12, result: 'succeeded', ok: true }] : [], decisions: [], outputs: [],
  evidence: kind === 'developer' ? [{ id: 'sub-1', kind: 'submission', title: 'Submission 1', ref: 'sub-1' }] : [],
  usage: { inputTokens: 10, outputTokens: 5, totalTokens: 15, estimatedCost: 0.001,
    llmCalls: 1, retries: 0, totalLatencyMs: 100, latency: { llmMs: 100, toolsMs: 12, testsMs: 0 } },
  optimizationSignals: [],
});

describe('LangGraph-backed Pixel Office and Inspector', () => {
  it('renders backend trace once across cursor replay without debug controls', async () => {
    mocks.inspection.mockResolvedValue({
      agent_debug: { manager: agent('manager'), developer: agent('developer'), reviewer: agent('reviewer') },
      office_poses: { manager: 'idle', developer: 'idle', reviewer: 'idle' },
    });
    const view = render(<OfficeExperienceView projectId="project" runId="run" cursor={42} connection="connected" runState="running:develop:task-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Select Developer in office' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Execution Trace' }));
    await waitFor(() => expect(screen.getAllByText('Tool request: read')).toHaveLength(1));
    fireEvent.click(screen.getByRole('tab', { name: 'Tools' }));
    expect(screen.getByText('greeting.txt')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Evidence' }));
    expect(screen.getByText('Submission 1')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Usage' }));
    expect(screen.getByText('15')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Execution Trace' }));
    expect(screen.queryByText('MOCK DATA')).toBeNull();
    expect(screen.queryByText('DEV CONTROLS')).toBeNull();
    view.rerender(<OfficeExperienceView projectId="project" runId="run" cursor={43} connection="connected" runState="running:develop:task-1" />);
    await waitFor(() => expect(mocks.inspection).toHaveBeenCalledTimes(2));
    expect(screen.getAllByText('Tool request: read')).toHaveLength(1);
  });
});
