"use client";

import { Line, LineChart, YAxis } from "recharts";

import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";

const config = { value: { label: "값", color: "var(--chart-1)" } } satisfies ChartConfig;

type Missing =
  /** 빠진 값을 이 값으로 채워 그리고, 툴팁에는 label을 보여준다(예: 순위권 밖 → 바닥선) */
  | { value: number; label: string }
  /** 빠진 구간은 앞뒤 값을 이어서 그린다 */
  | "connect";

type Props = {
  times: string[];
  values: (number | null)[];
  /** 순위처럼 작을수록 좋은 값이면 true(1위가 위로) */
  invert?: boolean;
  missing: Missing;
  formatTime: (iso: string) => string;
  formatValue: (v: number) => string;
  /** 스크린리더용 요약 */
  label: string;
};

/** 표 한 줄 안의 작은 추이선. 단일 계열이라 범례 없이 열 제목이 이름을 대신한다. */
export default function Sparkline({ times, values, invert = false, missing, formatTime, formatValue, label }: Props) {
  const fill = missing === "connect" ? null : missing;
  const points = times.map((t, i) => {
    const raw = values[i] ?? null;
    return { t, raw, value: raw ?? fill?.value ?? null };
  });
  if (points.filter((p) => p.raw != null).length < 2) {
    return <span className="text-[10px] text-zinc-400">수집 중</span>;
  }
  return (
    <ChartContainer config={config} className="aspect-auto h-8 w-full" role="img" aria-label={label}>
      <LineChart data={points} margin={{ top: 3, right: 3, bottom: 3, left: 3 }}>
        <YAxis hide reversed={invert} domain={["dataMin", "dataMax"]} />
        <ChartTooltip
          cursor={false}
          allowEscapeViewBox={{ x: true, y: true }}
          wrapperStyle={{ zIndex: 20 }}
          content={
            <ChartTooltipContent
              hideIndicator
              labelFormatter={(_, payload) => formatTime(String(payload?.[0]?.payload?.t ?? ""))}
              formatter={(_, __, item) => {
                const raw = (item?.payload as { raw: number | null } | undefined)?.raw;
                return <span className="font-mono tabular-nums">{raw != null ? formatValue(raw) : (fill?.label ?? "—")}</span>;
              }}
            />
          }
        />
        <Line
          dataKey="value"
          type="monotone"
          stroke="var(--color-value)"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 3 }}
          connectNulls={missing === "connect"}
          isAnimationActive={false}
        />
      </LineChart>
    </ChartContainer>
  );
}
