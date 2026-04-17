import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '../ui/App';

describe('App', () => {
  it('opens with the default layout already loaded and ready to run', async () => {
    render(<App />);

    expect(screen.getByText(/10 \/ 10 units placed/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /batch run/i })).toBeEnabled();
    expect(screen.getByRole('combobox', { name: /player behavior/i })).toHaveValue('balanced');
    expect(screen.getByRole('combobox', { name: /dm behavior/i })).toHaveValue('combined');
    expect(screen.getByRole('spinbutton', { name: /batch size/i })).toHaveValue(100);
    expect(screen.getByRole('grid', { name: /placement grid/i })).toBeInTheDocument();
  });

  it('uses batch size 1 as a replayable single encounter run', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.selectOptions(screen.getByRole('combobox', { name: /dm behavior/i }), 'balanced');
    const batchSizeInput = screen.getByRole('spinbutton', { name: /batch size/i });
    await user.clear(batchSizeInput);
    await user.type(batchSizeInput, '1');
    await user.click(screen.getByRole('button', { name: /batch run/i }));

    expect(await screen.findByText(/Replay Frame 1/i)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /combat grid/i })).toBeInTheDocument();
    expect(screen.getByText(/Per-Round Event Log/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Level 1 Fighter Sample Build/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Runs/i).length).toBeGreaterThan(0);
  });

  it('lets the user return from replay to edit the layout', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.selectOptions(screen.getByRole('combobox', { name: /dm behavior/i }), 'balanced');
    const batchSizeInput = screen.getByRole('spinbutton', { name: /batch size/i });
    await user.clear(batchSizeInput);
    await user.type(batchSizeInput, '1');
    await user.click(screen.getByRole('button', { name: /batch run/i }));
    await screen.findByRole('img', { name: /combat grid/i });

    await user.click(screen.getByRole('button', { name: /edit layout/i }));

    expect(screen.getByRole('grid', { name: /placement grid/i })).toBeInTheDocument();
    expect(screen.getByText(/Selected unit:/i)).toBeInTheDocument();
    expect(screen.queryByText(/Replay Frame 1/i)).not.toBeInTheDocument();
  });

  it('shows combined DM summaries for balanced players in a batch run', async () => {
    const user = userEvent.setup();
    render(<App />);

    const batchSizeInput = screen.getByRole('spinbutton', { name: /batch size/i });
    await user.clear(batchSizeInput);
    await user.type(batchSizeInput, '2');
    await user.click(screen.getByRole('button', { name: /batch run/i }));

    expect((await screen.findAllByText(/Smart Player Win Rate/i)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Dumb Player Win Rate/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Player Policy/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Kind DM/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Balanced DM/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Evil DM/i).length).toBeGreaterThan(0);
  });
});
