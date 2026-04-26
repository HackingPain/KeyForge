import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CredentialManager from '../components/CredentialManager';

describe('CredentialManager', () => {
  let mockApi;

  const mockCredentials = [
    {
      id: '1',
      api_name: 'openai',
      status: 'active',
      environment: 'production',
      api_key_preview: 'sk-...abc123',
      last_tested: '2025-12-01T10:00:00Z',
    },
    {
      id: '2',
      api_name: 'stripe',
      status: 'expired',
      environment: 'development',
      api_key_preview: 'sk_test_...xyz',
      last_tested: null,
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    window.confirm.mockReturnValue(true);
    mockApi = {
      get: jest.fn().mockImplementation((url) => {
        if (url === '/credentials') {
          return Promise.resolve({ data: mockCredentials });
        }
        if (url === '/api-catalog') {
          return Promise.resolve({
            data: {
              apis: [
                { id: 'openai', name: 'OpenAI' },
                { id: 'stripe', name: 'Stripe' },
                { id: 'github', name: 'GitHub' },
                { id: 'supabase', name: 'Supabase' },
              ],
            },
          });
        }
        if (url === '/walkthroughs') {
          return Promise.resolve({ data: [] });
        }
        if (url === '/issuers/github/installations') {
          return Promise.resolve({ data: { installations: [] } });
        }
        return Promise.resolve({ data: {} });
      }),
      post: jest.fn().mockResolvedValue({ data: {} }),
      put: jest.fn().mockResolvedValue({ data: {} }),
      delete: jest.fn().mockResolvedValue({ data: {} }),
    };
  });

  test('renders credential list', async () => {
    render(<CredentialManager api={mockApi} />);

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });
    expect(screen.getByText('stripe')).toBeInTheDocument();
    expect(screen.getByText('Credential Management')).toBeInTheDocument();
  });

  test('add credential form works', async () => {
    render(<CredentialManager api={mockApi} />);

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    // Click Add Credential button
    fireEvent.click(screen.getByText('Add Credential'));

    // Fill the form - select API Name. Use a provider that has neither a
    // walkthrough nor a registered issuer so the bare paste form renders.
    const apiSelect = screen.getByLabelText('API Name');
    fireEvent.change(apiSelect, { target: { value: 'supabase' } });

    // Fill API key
    const apiKeyInput = screen.getByPlaceholderText('Enter API key');
    fireEvent.change(apiKeyInput, { target: { value: 'sb_test123456' } });

    // Select environment
    const envSelect = screen.getByLabelText('Environment');
    fireEvent.change(envSelect, { target: { value: 'staging' } });

    // Submit the form - use the submit button within the form
    const submitButtons = screen.getAllByText('Add Credential');
    const submitButton = submitButtons[submitButtons.length - 1]; // The form submit button
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith('/credentials', {
        api_name: 'supabase',
        api_key: 'sb_test123456',
        environment: 'staging',
      });
    });
  });

  test('selecting github routes to GitHubConnect instead of the bare form', async () => {
    render(<CredentialManager api={mockApi} />);
    await waitFor(() => expect(screen.getByText('openai')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Add Credential'));
    fireEvent.change(screen.getByLabelText('API Name'), { target: { value: 'github' } });

    // GitHubConnect's loading or empty state shows; the bare paste field does not.
    await waitFor(() => {
      expect(screen.queryByPlaceholderText('Enter API key')).not.toBeInTheDocument();
    });
  });

  test('delete credential works', async () => {
    render(<CredentialManager api={mockApi} />);

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    // Click Delete on first credential
    const deleteButtons = screen.getAllByText('Delete');
    fireEvent.click(deleteButtons[0]);

    expect(window.confirm).toHaveBeenCalledWith('Are you sure you want to delete this credential?');

    await waitFor(() => {
      expect(mockApi.delete).toHaveBeenCalledWith('/credentials/1');
    });
  });

  test('test credential button works', async () => {
    mockApi.post.mockResolvedValueOnce({
      data: { test_result: { status: 'active', message: 'Key is valid' } },
    });

    render(<CredentialManager api={mockApi} />);

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    // Click Test on first credential
    const testButtons = screen.getAllByText('Test');
    fireEvent.click(testButtons[0]);

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith('/credentials/1/test');
    });

    await waitFor(() => {
      expect(screen.getByText('Key is valid')).toBeInTheDocument();
    });
  });

  test('shows masked key previews', async () => {
    render(<CredentialManager api={mockApi} />);

    await waitFor(() => {
      expect(screen.getByText('sk-...abc123')).toBeInTheDocument();
    });
    expect(screen.getByText('sk_test_...xyz')).toBeInTheDocument();
  });

  test('handles API errors gracefully', async () => {
    mockApi.get.mockImplementation((url) => {
      if (url === '/credentials') {
        return Promise.reject({
          response: { data: { detail: 'Failed to load credentials.' } },
        });
      }
      if (url === '/api-catalog') {
        return Promise.resolve({ data: { apis: [] } });
      }
      return Promise.resolve({ data: {} });
    });

    render(<CredentialManager api={mockApi} />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load credentials.')).toBeInTheDocument();
    });
  });

  test('shows empty state when no credentials exist', async () => {
    mockApi.get.mockImplementation((url) => {
      if (url === '/credentials') {
        return Promise.resolve({ data: [] });
      }
      if (url === '/api-catalog') {
        return Promise.resolve({ data: { apis: [] } });
      }
      return Promise.resolve({ data: {} });
    });

    render(<CredentialManager api={mockApi} />);

    await waitFor(() => {
      expect(
        screen.getByText(/No credentials added yet/)
      ).toBeInTheDocument();
    });
  });

  test('cancel button hides the add form', async () => {
    render(<CredentialManager api={mockApi} />);

    await waitFor(() => {
      expect(screen.getByText('Credential Management')).toBeInTheDocument();
    });

    // Open form
    fireEvent.click(screen.getByText('Add Credential'));
    expect(screen.getByPlaceholderText('Enter API key')).toBeInTheDocument();

    // Cancel
    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.queryByPlaceholderText('Enter API key')).not.toBeInTheDocument();
  });
});
