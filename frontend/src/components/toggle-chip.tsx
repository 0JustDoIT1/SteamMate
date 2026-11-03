"use client";

/**
 * 켜고 끄는 필터 칩. 켜짐은 채운 배경 + ✓, 꺼짐은 테두리 + "+"라 상태가 한눈에 구분된다.
 * 이름은 짧게 두고, 켰을 때의 뜻은 title(마우스를 올리면 보이는 설명)로 알려 준다.
 */
export default function ToggleChip({
  label,
  pressed,
  onChange,
  disabled = false,
  title,
}: {
  label: string;
  pressed: boolean;
  onChange: (pressed: boolean) => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      disabled={disabled}
      title={title}
      onClick={() => onChange(!pressed)}
      className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        pressed
          ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
          : "border-zinc-300 text-zinc-600 hover:border-zinc-500 dark:border-zinc-700 dark:text-zinc-400"
      }`}
    >
      <span aria-hidden className="w-3 text-center">
        {pressed ? "✓" : "+"}
      </span>
      {label}
    </button>
  );
}
