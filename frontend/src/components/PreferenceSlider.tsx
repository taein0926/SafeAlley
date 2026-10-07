import { useId } from "react";
import { PREFERENCE_LEVELS, preferenceLevelLabel, snapPreferenceWeight } from "../preferenceLevels";

type Props = {
  label: string;
  value: number;
  onChange: (value: number) => void;
  levelLabels?: readonly [string, string, string];
};

export function PreferenceSlider({ label, value, onChange, levelLabels }: Props) {
  const id = useId();
  const selected = snapPreferenceWeight(value);
  return (
    <div className="preference-slider">
      <label className="preference-slider-heading" htmlFor={id}>
        <span>{label}</span><output htmlFor={id}>{preferenceLevelLabel(selected, levelLabels)}</output>
      </label>
      <input
        id={id} aria-label={label} aria-valuetext={preferenceLevelLabel(selected, levelLabels)}
        type="range" min="0" max="100" step="50" value={selected}
        onChange={(event) => onChange(snapPreferenceWeight(Number(event.target.value)))}
      />
      <div className="preference-slider-ticks" aria-hidden="true">
        {PREFERENCE_LEVELS.map((level, index) => (
          <span key={level.value} data-selected={level.value === selected}>{levelLabels?.[index] ?? level.label}</span>
        ))}
      </div>
    </div>
  );
}
