import { render, screen, fireEvent } from '@testing-library/react';
import JargonGlossary from '../components/JargonGlossary';
import { JARGON } from '../components/JargonTerm';

describe('JargonGlossary', () => {
  test('does not render when isOpen is false', () => {
    const { container } = render(<JargonGlossary isOpen={false} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  test('renders a dialog when open', () => {
    render(<JargonGlossary isOpen={true} onClose={() => {}} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Glossary')).toBeInTheDocument();
  });

  test('includes every term from the JARGON map', () => {
    render(<JargonGlossary isOpen={true} onClose={() => {}} />);
    const terms = Object.keys(JARGON);
    terms.forEach((term) => {
      const expectedId = `glossary-${term.replace(/\s+/g, '-')}`;
      const node = document.getElementById(expectedId);
      expect(node).not.toBeNull();
    });
  });

  test('renders terms alphabetically', () => {
    render(<JargonGlossary isOpen={true} onClose={() => {}} />);
    const sectionIds = Array.from(document.querySelectorAll('[id^="glossary-"]')).map(
      (n) => n.id
    );
    const expected = Object.keys(JARGON)
      .sort((a, b) => a.localeCompare(b))
      .map((t) => `glossary-${t.replace(/\s+/g, '-')}`);
    expect(sectionIds).toEqual(expected);
  });

  test('clicking the close button calls the onClose handler', () => {
    const onClose = jest.fn();
    render(<JargonGlossary isOpen={true} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('Close glossary'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test('clicking the backdrop calls the onClose handler', () => {
    const onClose = jest.fn();
    render(<JargonGlossary isOpen={true} onClose={onClose} />);
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test('clicking inside the modal does not close it', () => {
    const onClose = jest.fn();
    render(<JargonGlossary isOpen={true} onClose={onClose} />);
    fireEvent.click(screen.getByText('Glossary'));
    expect(onClose).not.toHaveBeenCalled();
  });
});
