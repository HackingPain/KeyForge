import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import Profile from '../components/Profile';

function makeApi() {
  return {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  };
}

describe('Profile component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.getItem.mockReturnValue(null);
  });

  test('renders username from GET /auth/me', async () => {
    const api = makeApi();
    api.get.mockResolvedValue({ data: { id: 'u1', username: 'alice' } });

    await act(async () => {
      render(
        <Profile
          api={api}
          advancedEnabled={false}
          onToggleAdvanced={() => {}}
          onLogout={() => {}}
        />
      );
    });

    await waitFor(() =>
      expect(screen.getByTestId('profile-username')).toHaveTextContent('alice')
    );
    expect(api.get).toHaveBeenCalledWith('/auth/me');
  });

  test('toggling advanced calls onToggleAdvanced', async () => {
    const api = makeApi();
    api.get.mockResolvedValue({ data: { id: 'u1', username: 'bob' } });
    const onToggleAdvanced = jest.fn();

    await act(async () => {
      render(
        <Profile
          api={api}
          advancedEnabled={false}
          onToggleAdvanced={onToggleAdvanced}
          onLogout={() => {}}
        />
      );
    });

    await waitFor(() => expect(screen.getByTestId('profile-username')).toBeInTheDocument());

    const toggle = screen.getByLabelText('Show advanced features');
    expect(toggle.checked).toBe(false);

    await act(async () => { fireEvent.click(toggle); });

    expect(onToggleAdvanced).toHaveBeenCalledTimes(1);
  });

  test('logout calls onLogout prop', async () => {
    const api = makeApi();
    api.get.mockResolvedValue({ data: { id: 'u1', username: 'carol' } });
    const onLogout = jest.fn().mockResolvedValue(undefined);

    await act(async () => {
      render(
        <Profile
          api={api}
          advancedEnabled={true}
          onToggleAdvanced={() => {}}
          onLogout={onLogout}
        />
      );
    });

    await waitFor(() => expect(screen.getByTestId('profile-username')).toBeInTheDocument());

    await act(async () => { fireEvent.click(screen.getByText('Logout')); });

    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  test('logout falls back to api.post(/auth/logout) when no onLogout provided', async () => {
    const api = makeApi();
    api.get.mockResolvedValue({ data: { id: 'u1', username: 'dave' } });
    api.post.mockResolvedValue({ data: { status: 'ok' } });

    // Stub window.location.reload so jsdom does not navigate.
    const originalLocation = window.location;
    delete window.location;
    window.location = { ...originalLocation, reload: jest.fn() };

    try {
      await act(async () => {
        render(
          <Profile
            api={api}
            advancedEnabled={false}
            onToggleAdvanced={() => {}}
          />
        );
      });

      await waitFor(() => expect(screen.getByTestId('profile-username')).toBeInTheDocument());

      await act(async () => { fireEvent.click(screen.getByText('Logout')); });

      await waitFor(() => expect(api.post).toHaveBeenCalledWith('/auth/logout'));
    } finally {
      window.location = originalLocation;
    }
  });

  test('advanced toggle reflects advancedEnabled prop', async () => {
    const api = makeApi();
    api.get.mockResolvedValue({ data: { id: 'u1', username: 'eve' } });

    await act(async () => {
      render(
        <Profile
          api={api}
          advancedEnabled={true}
          onToggleAdvanced={() => {}}
          onLogout={() => {}}
        />
      );
    });

    await waitFor(() => expect(screen.getByTestId('profile-username')).toBeInTheDocument());
    const toggle = screen.getByLabelText('Show advanced features');
    expect(toggle.checked).toBe(true);
  });
});
