import { render, screen, fireEvent } from '@testing-library/react';
import JargonTerm, { JARGON } from '../components/JargonTerm';

describe('JargonTerm', () => {
  test('renders the term inline with a dotted underline', () => {
    render(<JargonTerm term="TOTP">TOTP</JargonTerm>);
    const trigger = screen.getByText('TOTP');
    expect(trigger).toBeInTheDocument();
    expect(trigger.className).toMatch(/border-dotted/);
    expect(trigger.className).toMatch(/cursor-help/);
  });

  test('hovering reveals the tooltip with the plain-language definition', () => {
    render(<JargonTerm term="TOTP">TOTP</JargonTerm>);
    const trigger = screen.getByText('TOTP');

    // Tooltip body is not in the DOM until hover.
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    // The MouseEnter handler is on the wrapper span, which is the trigger's parent.
    fireEvent.mouseEnter(trigger.parentElement);

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toBeInTheDocument();
    // Renders the definition for the requested term verbatim from the JARGON map.
    expect(tooltip.textContent).toContain(JARGON.totp);
  });

  test('hides the tooltip on mouse leave', () => {
    render(<JargonTerm term="MFA">MFA</JargonTerm>);
    const wrapper = screen.getByText('MFA').parentElement;

    fireEvent.mouseEnter(wrapper);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    fireEvent.mouseLeave(wrapper);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  test('clicking "Learn more" opens the glossary modal', () => {
    render(<JargonTerm term="KMS">KMS</JargonTerm>);
    const wrapper = screen.getByText('KMS').parentElement;

    fireEvent.mouseEnter(wrapper);
    const learnMore = screen.getByText('Learn more');
    fireEvent.click(learnMore);

    // Modal renders a dialog with a Glossary heading.
    const modal = screen.getByRole('dialog');
    expect(modal).toBeInTheDocument();
    expect(screen.getByText('Glossary')).toBeInTheDocument();
  });

  test('renders verbatim children when term is unknown', () => {
    const { container } = render(<JargonTerm term="not-a-real-term">hello world</JargonTerm>);
    expect(container.textContent).toBe('hello world');
    // No tooltip wrapper.
    expect(container.querySelector('.border-dotted')).toBeNull();
  });

  test('uses the term itself as the displayed label when no children are passed', () => {
    render(<JargonTerm term="JWT" />);
    expect(screen.getByText('JWT')).toBeInTheDocument();
  });

  test('look-up is case-insensitive', () => {
    render(<JargonTerm term="totp">totp</JargonTerm>);
    const wrapper = screen.getByText('totp').parentElement;
    fireEvent.mouseEnter(wrapper);
    expect(screen.getByRole('tooltip').textContent).toContain(JARGON.totp);
  });
});
