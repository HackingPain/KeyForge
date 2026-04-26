import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CredentialWalkthrough from '../components/CredentialWalkthrough';

const fixture = {
  provider: 'stripe',
  display_name: 'Stripe',
  description: 'Stripe is a payments platform.',
  icon: 'stripe',
  credential_label: 'Restricted API key',
  validation: {
    regex: '^rk_(test|live)_[A-Za-z0-9]{24,}$',
    min_length: 32,
    max_length: 128,
  },
  suggested_scopes: [
    { value: 'read_only', label: 'Read only (recommended)' },
    { value: 'read_write', label: 'Read and write' },
  ],
  steps: [
    {
      title: 'Open the Stripe dashboard',
      description: 'Sign in to Stripe and go to API keys.',
      action: {
        type: 'external_link',
        url: 'https://dashboard.stripe.com/apikeys',
        label: 'Open Stripe dashboard',
      },
    },
    {
      title: 'Create a restricted key',
      description: 'Click Create restricted key and pick a descriptive name.',
    },
    {
      title: 'Paste the key',
      description: 'Copy the key from Stripe and paste it below.',
      action: { type: 'paste_credential' },
    },
  ],
};

describe('CredentialWalkthrough', () => {
  let mockApi;
  let mockOnComplete;
  let mockOnCancel;
  let originalOpen;

  beforeEach(() => {
    jest.clearAllMocks();
    mockOnComplete = jest.fn();
    mockOnCancel = jest.fn();
    originalOpen = window.open;
    window.open = jest.fn();
    mockApi = {
      get: jest.fn().mockImplementation((url) => {
        if (url === '/walkthroughs/stripe') {
          return Promise.resolve({ data: fixture });
        }
        return Promise.resolve({ data: {} });
      }),
      post: jest.fn().mockResolvedValue({ data: {} }),
      put: jest.fn().mockResolvedValue({ data: {} }),
      delete: jest.fn().mockResolvedValue({ data: {} }),
    };
  });

  afterEach(() => {
    window.open = originalOpen;
  });

  test('renders the first step after fetching the walkthrough', async () => {
    render(
      <CredentialWalkthrough
        api={mockApi}
        provider="stripe"
        onComplete={mockOnComplete}
        onCancel={mockOnCancel}
      />
    );

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/walkthroughs/stripe');
    });

    expect(
      await screen.findByText('Open the Stripe dashboard')
    ).toBeInTheDocument();
    expect(screen.getByText(/Step 1 of 3/)).toBeInTheDocument();
    expect(screen.getByText('Open Stripe dashboard')).toBeInTheDocument();
  });

  test('advances through every step to the paste step', async () => {
    render(
      <CredentialWalkthrough
        api={mockApi}
        provider="stripe"
        onComplete={mockOnComplete}
        onCancel={mockOnCancel}
      />
    );

    await screen.findByText('Open the Stripe dashboard');

    // Step 1: external link button should advance the stepper
    fireEvent.click(screen.getByText('Open Stripe dashboard'));
    expect(window.open).toHaveBeenCalledWith(
      'https://dashboard.stripe.com/apikeys',
      '_blank',
      'noopener,noreferrer'
    );

    await screen.findByText('Create a restricted key');
    expect(screen.getByText(/Step 2 of 3/)).toBeInTheDocument();

    // Step 2: no action -> Next button advances
    fireEvent.click(screen.getByText('Next'));

    await screen.findByText('Paste the key');
    expect(screen.getByText(/Step 3 of 3/)).toBeInTheDocument();
    expect(
      screen.getByLabelText('Restricted API key')
    ).toBeInTheDocument();
  });

  test('validate then save calls the API and onComplete', async () => {
    mockApi.post.mockImplementation((url) => {
      if (url === '/walkthroughs/stripe/validate') {
        return Promise.resolve({ data: { valid: true, reason: null } });
      }
      if (url === '/credentials') {
        return Promise.resolve({
          data: {
            id: 'cred-1',
            api_name: 'stripe',
            api_key_preview: '****AAAA',
            status: 'format_valid',
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(
      <CredentialWalkthrough
        api={mockApi}
        provider="stripe"
        onComplete={mockOnComplete}
        onCancel={mockOnCancel}
      />
    );

    // Walk to the paste step.
    await screen.findByText('Open the Stripe dashboard');
    fireEvent.click(screen.getByText('Open Stripe dashboard'));
    await screen.findByText('Create a restricted key');
    fireEvent.click(screen.getByText('Next'));
    await screen.findByText('Paste the key');

    const credentialField = screen.getByLabelText('Restricted API key');
    const pastedValue = 'rk_test_' + 'A'.repeat(32);
    fireEvent.change(credentialField, { target: { value: pastedValue } });

    fireEvent.click(screen.getByText('Validate'));

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith(
        '/walkthroughs/stripe/validate',
        { credential: pastedValue }
      );
    });

    await screen.findByText(/Looks good/);

    fireEvent.click(screen.getByText('Save credential'));

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith('/credentials', {
        api_name: 'stripe',
        api_key: pastedValue,
        environment: 'development',
      });
    });

    await waitFor(() => {
      expect(mockOnComplete).toHaveBeenCalledTimes(1);
    });
  });

  test('shows a reason when validation fails', async () => {
    mockApi.post.mockResolvedValue({
      data: { valid: false, reason: 'Credential does not match the expected format for Stripe.' },
    });

    render(
      <CredentialWalkthrough
        api={mockApi}
        provider="stripe"
        onComplete={mockOnComplete}
        onCancel={mockOnCancel}
      />
    );

    await screen.findByText('Open the Stripe dashboard');
    fireEvent.click(screen.getByText('Open Stripe dashboard'));
    await screen.findByText('Create a restricted key');
    fireEvent.click(screen.getByText('Next'));
    await screen.findByText('Paste the key');

    const credentialField = screen.getByLabelText('Restricted API key');
    fireEvent.change(credentialField, { target: { value: 'totally-wrong' } });
    fireEvent.click(screen.getByText('Validate'));

    await screen.findByText(/does not match/);
    // Save must remain disabled when validation fails.
    expect(screen.getByText('Save credential')).toBeDisabled();
  });

  test('back button returns to the previous step', async () => {
    render(
      <CredentialWalkthrough
        api={mockApi}
        provider="stripe"
        onComplete={mockOnComplete}
        onCancel={mockOnCancel}
      />
    );

    await screen.findByText('Open the Stripe dashboard');
    fireEvent.click(screen.getByText('Open Stripe dashboard'));
    await screen.findByText('Create a restricted key');

    fireEvent.click(screen.getByText('Back'));
    await screen.findByText('Open the Stripe dashboard');
    expect(screen.getByText(/Step 1 of 3/)).toBeInTheDocument();
  });

  test('shows an error if the walkthrough cannot be loaded', async () => {
    mockApi.get.mockRejectedValue({
      response: { data: { detail: 'No walkthrough defined for provider stripe.' } },
    });

    render(
      <CredentialWalkthrough
        api={mockApi}
        provider="stripe"
        onComplete={mockOnComplete}
        onCancel={mockOnCancel}
      />
    );

    await screen.findByText(/No walkthrough defined/);
  });
});
