import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import GitHubConnect from '../components/GitHubConnect';

describe('GitHubConnect', () => {
  let mockApi;
  let mockOnMinted;
  let originalOpen;

  beforeEach(() => {
    jest.clearAllMocks();
    mockOnMinted = jest.fn();
    originalOpen = window.open;
    window.open = jest.fn();
    // Reset history search so the connected/error effect does not fire.
    window.history.replaceState({}, '', '/');
    mockApi = {
      get: jest.fn(),
      post: jest.fn(),
    };
  });

  afterEach(() => {
    window.open = originalOpen;
  });

  test('renders Connect GitHub button when there are no installations', async () => {
    mockApi.get.mockImplementation((url) => {
      if (url === '/issuers/github/installations') {
        return Promise.resolve({ data: { installations: [] } });
      }
      return Promise.resolve({ data: {} });
    });

    render(<GitHubConnect api={mockApi} onCredentialMinted={mockOnMinted} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /connect github/i })).toBeInTheDocument();
    });

    expect(mockApi.get).toHaveBeenCalledWith('/issuers/github/installations');
  });

  test('clicking Connect GitHub posts to /start and opens the install URL', async () => {
    mockApi.get.mockResolvedValue({ data: { installations: [] } });
    mockApi.post.mockResolvedValue({
      data: { install_url: 'https://github.com/apps/keyforge-test/installations/new?state=abc' },
    });

    render(<GitHubConnect api={mockApi} onCredentialMinted={mockOnMinted} />);

    const button = await screen.findByRole('button', { name: /connect github/i });
    fireEvent.click(button);

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith('/issuers/github/start');
    });

    await waitFor(() => {
      expect(window.open).toHaveBeenCalledWith(
        'https://github.com/apps/keyforge-test/installations/new?state=abc',
        '_blank',
        'noopener,noreferrer'
      );
    });
  });

  test('shows mint form when installations exist and posts to /mint', async () => {
    mockApi.get.mockResolvedValue({ data: { installations: ['12345'] } });
    mockApi.post.mockResolvedValue({
      data: { id: 'cred-1', issuer: 'github', scope: 'repo:acme/widgets' },
    });

    render(<GitHubConnect api={mockApi} onCredentialMinted={mockOnMinted} />);

    // Wait until the form is rendered.
    const repoInput = await screen.findByPlaceholderText('acme/widgets');
    fireEvent.change(repoInput, { target: { value: 'acme/widgets' } });

    const generateBtn = screen.getByRole('button', { name: /generate credential/i });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith('/issuers/github/mint', {
        repo: 'acme/widgets',
        permissions: { contents: 'read', metadata: 'read' },
      });
    });

    await waitFor(() => {
      expect(mockOnMinted).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'cred-1', issuer: 'github' })
      );
    });

    // Toast is visible.
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/credential minted/i);
    });

    // PAT itself is never displayed in the UI.
    expect(screen.queryByText(/ghs_/i)).not.toBeInTheDocument();
  });

  test('shows an error if the mint endpoint fails', async () => {
    mockApi.get.mockResolvedValue({ data: { installations: ['12345'] } });
    mockApi.post.mockRejectedValue({
      response: { data: { detail: 'GitHub rejected the request' } },
    });

    render(<GitHubConnect api={mockApi} onCredentialMinted={mockOnMinted} />);

    const repoInput = await screen.findByPlaceholderText('acme/widgets');
    fireEvent.change(repoInput, { target: { value: 'acme/widgets' } });
    fireEvent.click(screen.getByRole('button', { name: /generate credential/i }));

    await waitFor(() => {
      expect(screen.getByText(/github rejected the request/i)).toBeInTheDocument();
    });
    expect(mockOnMinted).not.toHaveBeenCalled();
  });

  test('rejects a malformed repo input client-side', async () => {
    mockApi.get.mockResolvedValue({ data: { installations: ['12345'] } });

    render(<GitHubConnect api={mockApi} onCredentialMinted={mockOnMinted} />);

    const repoInput = await screen.findByPlaceholderText('acme/widgets');
    // The HTML5 form validation requires a non-empty value; supply one but
    // without a slash so the client-side check trips.
    fireEvent.change(repoInput, { target: { value: 'no-slash-here' } });
    fireEvent.click(screen.getByRole('button', { name: /generate credential/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/repository must be in/i)
      ).toBeInTheDocument();
    });
    expect(mockApi.post).not.toHaveBeenCalled();
  });
});
