// A labelled numeric input bound to a params object. `title` is the hover help.
export default function NumberField({ label, title, value, onChange, disabled, ...rest }) {
  return (
    <div className="field">
      <label title={title}>{label}</label>
      <input
        type="number"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        {...rest}
      />
    </div>
  );
}
