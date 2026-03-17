import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Dashboard from '../components/Dashboard';

describe('Dashboard', () => {
  let mockApi;

  beforeEach(() => {
    jest.clearAllMocks();
    mockApi = {
      get: jest.fn(),
      post: jest.fn().mockResolvedValue({ data: {} }),
      put: jest.fn().mockResolvedValue({ data: {} }),
      delete: jest.fn().mockResolvedValue({ data: {} }),
    };
  });

  test('renders loading state initially', () => {
    mockApi.get.mockReturnValue(new Promise(() => {})); // Never resolves
    render(<Dashboard api={mockApi} />);
    expect(screen.getByText('Loading dashboard...')).toBeInTheDocument();
  });

  test('displays stats after loading', async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        total_credentials: 12,
        status_breakdown: {
          active: 8,
          invalid: 2,
          expired: 1,
        },
        health_score: 85,
      },
    });

    render(<Dashboard api={mockApi} />);

    await waitFor(() => {
      expect(screen.getByText('12')).toBeInTheDocument();
    });
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('85%')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument(); // 2 invalid + 1 expired
    expect(screen.getByText('Total Credentials')).toBeInTheDocument();
    expect(screen.getByText('Active APIs')).toBeInTheDocument();
    expect(screen.getByText('Health Score')).toBeInTheDocument();
    expect(screen.getByText('Issues')).toBeInTheDocument();
  });

  test('shows error state on API failure', async () => {
    mockApi.get.mockRejectedValueOnce({
      response: { data: { detail: 'Server error occurred' } },
    });

    render(<Dashboard api={mockApi} />);

    await waitFor(() => {
      expect(screen.getByText('Server error occurred')).toBeInTheDocument();
    });
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  test('shows generic error message when no detail provided', async () => {
    mockApi.get.mockRejectedValueOnce(new Error('Network Error'));

    render(<Dashboard api={mockApi} />);

    await waitFor(() => {
      expect(screen.getByText('Network Error')).toBeInTheDocument();
    });
  });

  test('retry button works after error', async () => {
    // First call fails
    mockApi.get.mockRejectedValueOnce({
      response: { data: { detail: 'Temporary failure' } },
    });

    render(<Dashboard api={mockApi} />);

    await waitFor(() => {
      expect(screen.getByText('Temporary failure')).toBeInTheDocument();
    });

    // Set up successful response for retry
    mockApi.get.mockResolvedValueOnce({
      data: {
        total_credentials: 5,
        status_breakdown: { active: 3, invalid: 1, expired: 0 },
        health_score: 90,
      },
    });

    fireEvent.click(screen.getByText('Retry'));

    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument();
    });
    expect(screen.getByText('90%')).toBeInTheDocument();
  });

  test('calls /dashboard/overview endpoint on mount', () => {
    mockApi.get.mockReturnValue(new Promise(() => {}));
    render(<Dashboard api={mockApi} />);
    expect(mockApi.get).toHaveBeenCalledWith('/dashboard/overview');
  });
});
