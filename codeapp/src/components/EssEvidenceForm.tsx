import {
  narrativeFields,
  type EssEvidenceContext,
  type EssEvidenceOutcome,
  type NarrativeField,
  type NarrativeFieldKey,
} from "../lib/essEvidence";

const OUTCOME_LABEL: Record<EssEvidenceOutcome, string> = {
  working: "Working example",
  "non-working": "Non-working example",
};

export function EssEvidenceForm({ context, showFieldErrors, registerField, onChange }: {
  context: EssEvidenceContext;
  showFieldErrors: boolean;
  registerField: (key: NarrativeFieldKey, element: HTMLInputElement | HTMLTextAreaElement | null) => void;
  onChange: <K extends keyof EssEvidenceContext>(key: K, value: EssEvidenceContext[K]) => void;
}) {
  const fields = narrativeFields(context.outcome);
  const invalid = (field: NarrativeField) => showFieldErrors && field.required && !context[field.key].trim();

  return (
    <section className="ess-evidence-detail" aria-labelledby="ess-evidence-context-heading">
      <h3 id="ess-evidence-context-heading" className="sub ess-evidence-step">
        <span className="step-index">2</span>Describe the example
      </h3>
      <p className="muted small">
        {context.outcome === "working"
          ? "A working example needs a title and what the agent did correctly. Everything else is optional context."
          : "A non-working example needs a title, what happened, and what should have happened. Everything else is optional context."}
      </p>

      <fieldset className="ess-evidence-outcome">
        <legend>Classification</legend>
        {(Object.keys(OUTCOME_LABEL) as EssEvidenceOutcome[]).map((value) => (
          <label key={value} className="checkline">
            <input
              type="radio"
              name="ess-evidence-outcome"
              checked={context.outcome === value}
              onChange={() => onChange("outcome", value)}
            />
            {OUTCOME_LABEL[value]}
          </label>
        ))}
      </fieldset>

      {fields.map((field) => {
        const isInvalid = invalid(field);
        const errorId = `ess-evidence-error-${field.key}`;
        const shared = {
          ref: (element: HTMLInputElement & HTMLTextAreaElement | null) => registerField(field.key, element),
          value: context[field.key],
          placeholder: field.placeholder,
          onChange: (event: { target: { value: string } }) => onChange(field.key, event.target.value),
          "aria-invalid": isInvalid,
          "aria-describedby": isInvalid ? errorId : undefined,
        };
        return (
          <label key={field.key} className={`ess-evidence-field${isInvalid ? " invalid" : ""}`}>
            <span>
              {field.label}
              {field.required
                ? <em className="req">Required</em>
                : field.optionalHint && <small className="muted"> {field.optionalHint}</small>}
            </span>
            {field.multiline
              ? <textarea rows={3} {...shared} />
              : <input className="search" {...shared} />}
            {isInvalid && <small id={errorId} className="ess-evidence-field-error">{field.help}</small>}
          </label>
        );
      })}

      <label className="ess-evidence-field">
        <span>Referenced knowledge URLs<small className="muted"> optional · one per line</small></span>
        <textarea
          value={context.referencedKnowledgeUrls.join("\n")}
          onChange={(event) => onChange("referencedKnowledgeUrls", event.target.value.split("\n"))}
          rows={2}
        />
      </label>

      <label className="ess-evidence-field">
        <span>Expected knowledge URLs<small className="muted"> optional · one per line</small></span>
        <textarea
          value={context.expectedKnowledgeUrls.join("\n")}
          onChange={(event) => onChange("expectedKnowledgeUrls", event.target.value.split("\n"))}
          rows={2}
        />
      </label>

      <label className="ess-evidence-field">
        <span>Investigation notes<small className="muted"> optional</small></span>
        <textarea
          value={context.investigationNotes}
          onChange={(event) => onChange("investigationNotes", event.target.value)}
          rows={3}
        />
      </label>
    </section>
  );
}
