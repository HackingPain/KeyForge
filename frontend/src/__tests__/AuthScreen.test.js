import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AuthScreen from '../components/AuthScreen';

describe('AuthScreen', () => {
  let mockApi;
  let mockOnAuth;

  beforeEach(() => {
    jest.clearAllMocks();
    mockOnAuth = jest.fn();
    mockApi = {
      get: jest.fn().mockResolvedValue({ data: {} }),
      post: jest.fn().mockResolvedValue({ data: { access_token: 'mock-token-123' } }),
      put: jest.fn().mockResolvedValue({ data: {} }),
      delete: jest.fn().mockResolvedValue({ data: {} }),
    };
  });

  test('renders login form by default', () => {
    render(<AuthScreen api={mockApi} onAuth={mockOnAuth} />);
    expect(screen.getByText('KeyForge')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter your username')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter your password')).toBeInTheDocument();
    expect(screen.getByText('Sign In')).toBeInTheDocument();
  });

  test('can switch to register form', () => {
    render(<AuthScreen api={mockApi} onAuth={mockOnAuth} />);

    fireEvent.click(screen.getByText('Register'));

    expect(screen.getByText('Create Account')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Min 8 characters')).toBeInTheDocument();
  });

  test('login submits correct data', async () => {
    render(<AuthScreen api={mockApi} onAuth={mockOnAuth} />);

    fireEvent.change(screen.getByPlaceholderText('Enter your username'), {
      target: { value: 'testuser' },
    });
    fireEvent.change(screen.getByPlaceholderText('Enter your password'), {
      target: { value: 'testpassword123' },
    });
    fireEvent.click(screen.getByText('Sign In'));

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith(
        '/auth/login',
        expect.any(URLSearchParams),
        expect.objectContaining({
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        })
      );
    });
  });

  test('register submits correct data', async () => {
    render(<AuthScreen api={mockApi} onAuth={mockOnAuth} />);

    fireEvent.click(screen.getByText('Register'));

    fireEvent.change(screen.getByPlaceholderText('Enter your username'), {
      target: { value: 'newuser' },
    });
    fireEvent.change(screen.getByPlaceholderText('Min 8 characters'), {
      target: { value: 'newpassword123' },
    });
    fireEvent.click(screen.getByText('Create Account'));

    await waitFor(() => {
      // First call should be register
      expect(mockApi.post).toHaveBeenCalledWith('/auth/register', {
        username: 'newuser',
        password: 'newpassword123',
      });
    });

    await waitFor(() => {
      // Second call should be auto-login
      expect(mockApi.post).toHaveBeenCalledWith(
        '/auth/login',
        expect.any(URLSearchParams),
        expect.objectContaining({
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        })
      );
    });
  });

  test('shows error on failed login', async () => {
    mockApi.post.mockRejectedValueOnce({
      response: { data: { detail: 'Invalid credentials' } },
    });

    render(<AuthScreen api={mockApi} onAuth={mockOnAuth} />);

    fireEvent.change(screen.getByPlaceholderText('Enter your username'), {
      target: { value: 'baduser' },
    });
    fireEvent.change(screen.getByPlaceholderText('Enter your password'), {
      target: { value: 'wrongpassword' },
    });
    fireEvent.click(screen.getByText('Sign In'));

    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
    });
    expect(mockOnAuth).not.toHaveBeenCalled();
  });

  test('shows error on failed register', async () => {
    mockApi.post.mockRejectedValueOnce({
      response: { data: { detail: 'Username already exists' } },
    });

    render(<AuthScreen api={mockApi} onAuth={mockOnAuth} />);

    fireEvent.click(screen.getByText('Register'));

    fireEvent.change(screen.getByPlaceholderText('Enter your username'), {
      target: { value: 'existinguser' },
    });
    fireEvent.change(screen.getByPlaceholderText('Min 8 characters'), {
      target: { value: 'somepassword123' },
    });
    fireEvent.click(screen.getByText('Create Account'));

    await waitFor(() => {
      expect(screen.getByText('Username already exists')).toBeInTheDocument();
    });
    expect(mockOnAuth).not.toHaveBeenCalled();
  });

  test('calls onAuth with no arguments on successful login', async () => {
    mockApi.post.mockResolvedValueOnce({
      data: { access_token: 'my-jwt-token' },
    });

    render(<AuthScreen api={mockApi} onAuth={mockOnAuth} />);

    fireEvent.change(screen.getByPlaceholderText('Enter your username'), {
      target: { value: 'testuser' },
    });
    fireEvent.change(screen.getByPlaceholderText('Enter your password'), {
      target: { value: 'testpassword123' },
    });
    fireEvent.click(screen.getByText('Sign In'));

    await waitFor(() => {
      expect(mockOnAuth).toHaveBeenCalledWith();
    });
  });

  test('shows array error details correctly', async () => {
    mockApi.post.mockRejectedValueOnce({
      response: {
        data: {
          detail: [
            { msg: 'Username too short' },
            { msg: 'Password too weak' },
          ],
        },
      },
    });

    render(<AuthScreen api={mockApi} onAuth={mockOnAuth} />);

    fireEvent.change(screen.getByPlaceholderText('Enter your username'), {
      target: { value: 'ab' },
    });
    fireEvent.change(screen.getByPlaceholderText('Enter your password'), {
      target: { value: 'weak' },
    });
    fireEvent.click(screen.getByText('Sign In'));

    await waitFor(() => {
      expect(screen.getByText('Username too short, Password too weak')).toBeInTheDocument();
    });
  });
});
