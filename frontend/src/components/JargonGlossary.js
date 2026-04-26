import { useEffect, useRef } from "react";
import { JARGON } from "./JargonTerm";

const slugify = (term) => `glossary-${String(term).toLowerCase().replace(/\s+/g, "-")}`;

const displayTerm = (term) => {
  // Acronyms stay uppercase; multi-word phrases stay title-cased.
  if (term.length <= 4) return term.toUpperCase();
  return term
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
};

const JargonGlossary = ({ isOpen, onClose, initialTerm }) => {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return;
    if (initialTerm) {
      // Defer so the DOM exists before we scroll to the anchor.
      const id = slugify(initialTerm);
      const target = document.getElementById(id);
      if (target && typeof target.scrollIntoView === "function") {
        target.scrollIntoView({ block: "start" });
      }
    }
  }, [isOpen, initialTerm]);

  if (!isOpen) return null;

  const sortedTerms = Object.keys(JARGON).sort((a, b) => a.localeCompare(b));

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="KeyForge Glossary"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        ref={containerRef}
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[85vh] flex flex-col"
      >
        <div className="flex justify-between items-center px-6 py-4 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">Glossary</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close glossary"
            className="px-3 py-1 text-sm text-gray-500 hover:text-gray-800 border border-gray-200 rounded-md hover:bg-gray-50"
          >
            Close
          </button>
        </div>
        <div className="overflow-y-auto px-6 py-4 space-y-4">
          {sortedTerms.map((term) => (
            <div key={term} id={slugify(term)} className="scroll-mt-4">
              <h3 className="text-sm font-bold text-gray-900">{displayTerm(term)}</h3>
              <p className="text-sm text-gray-700 mt-1 leading-relaxed">{JARGON[term]}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default JargonGlossary;
