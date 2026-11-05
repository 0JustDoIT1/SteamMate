"use client";

import { useState } from "react";

import { type AskResponse, useAskNews } from "@/features/news/queries";
import { formatDateTime } from "@/lib/format";

const MAX_QUESTION = 300;
// 줄 수가 이보다 많은 자유 답변은 접어서 보여 준다
const COLLAPSE_LINES = 6;

// 자주 묻는 질문. Steam 공지는 대부분 패치 노트라 그에 맞는 질문만 둔다.
// "앞으로의 계획" 류는 시험해 보니 근거 없음·엉뚱한 답이 많아 넣지 않았다.
const QUESTION_TEMPLATES = ["최신 업데이트에서 바뀐 점은?", "새로 추가된 콘텐츠는?"];

// 모델이 공지의 날짜를 "2026-08-31T19:00:00"처럼 옮겨 적기도 해 읽기 쉽게 바꾼다(시간대 변환은 하지 않는다)
const ISO_LIKE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/;

function readableDate(s: string): string {
  const m = ISO_LIKE.exec(s.trim());
  if (!m) return s;
  const date = `${m[1]}. ${Number(m[2])}. ${Number(m[3])}.`;
  return m[4] && `${m[4]}:${m[5]}` !== "00:00" ? `${date} ${m[4]}:${m[5]}` : date;
}

/** 공식 공지를 근거로 한 AI 질문. 기능이 꺼진 환경에서는 안내만 보여 준다. */
export default function NewsAsk({ appid, enabled }: { appid: number; enabled: boolean }) {
  if (!enabled) {
    return (
      <section className="rounded-lg border border-zinc-200 px-4 py-3 text-sm text-zinc-500 dark:border-zinc-800">
        이 환경에서는 공지 AI 질문을 제공하지 않습니다.
      </section>
    );
  }
  return <AskForm appid={appid} />;
}

function AskForm({ appid }: { appid: number }) {
  const ask = useAskNews();
  const [question, setQuestion] = useState("");
  const trimmed = question.trim();

  function submit(text: string) {
    if (!text || ask.isPending) return;
    ask.mutate({ appid, question: text });
  }

  return (
    <section className="rounded-lg border border-zinc-200 dark:border-zinc-800">
      <header className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h2 className="font-semibold">공지에 질문하기</h2>
        <p className="text-xs text-zinc-500">
          최근 공식 공지(최대 50건)를 근거로 AI가 답합니다. &ldquo;최신 업데이트&rdquo;는 제목에 버전·패치가 들어간 가장
          최근 공지를 기준으로 합니다. 틀릴 수 있으니 출처의 원문을 확인하세요.
        </p>
      </header>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(trimmed);
        }}
        className="space-y-3 px-4 py-4"
      >
        <div className="flex flex-wrap gap-2">
          {QUESTION_TEMPLATES.map((t) => (
            <button
              key={t}
              type="button"
              disabled={ask.isPending}
              onClick={() => {
                setQuestion(t);
                submit(t);
              }}
              className="rounded-full border border-zinc-300 px-3 py-1 text-xs text-zinc-700 hover:border-zinc-500 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300"
            >
              {t}
            </button>
          ))}
        </div>
        <label className="block">
          <span className="sr-only">질문</span>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={MAX_QUESTION}
            rows={2}
            placeholder="예: (아이템 이름) 피해량은 지금 얼마야?"
            className="w-full resize-y rounded-md border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
          />
        </label>
        <div className="flex items-center gap-2 text-sm">
          <span className="ml-auto text-xs text-zinc-500">
            {question.length}/{MAX_QUESTION}
          </span>
          <button
            type="submit"
            disabled={!trimmed || ask.isPending}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {ask.isPending ? "답변 만드는 중…" : "질문"}
          </button>
        </div>
      </form>

      {ask.isPending ? (
        <p className="border-t border-zinc-200 px-4 py-3 text-sm text-zinc-500 dark:border-zinc-800">
          공지를 모아 답을 만드는 중입니다. 처음 질문하는 게임은 30초 이상 걸릴 수 있습니다.
        </p>
      ) : ask.isError ? (
        <p role="alert" className="border-t border-zinc-200 px-4 py-3 text-sm text-red-700 dark:border-zinc-800 dark:text-red-300">
          {ask.error.message}
        </p>
      ) : ask.data ? (
        // 질문마다 새로 그려 접기 상태를 초기화한다
        <Answer key={ask.data.answeredAt} data={ask.data} />
      ) : null}
    </section>
  );
}

function Answer({ data }: { data: AskResponse }) {
  // 최신 업데이트 공지가 이미 출처에 있으면 같은 공지를 두 번 보이지 않는다.
  // 모델이 다른 공지를 요약했을 때만 "무엇을 최신으로 봤는지" 알려 준다
  const latest = data.latestUpdate;
  const showLatest = latest !== null && latest !== undefined && !data.sources.some((s) => s.gid === latest.gid);
  return (
    <div className="space-y-3 border-t border-zinc-200 px-4 py-4 dark:border-zinc-800">
      {data.refused ? (
        // 서버가 질문 유형에 맞춘 안내 문장을 준다(내부 판정 말 "근거 없음"은 보이지 않는다)
        <p className="text-sm text-zinc-500">{data.answer}</p>
      ) : data.summary ? (
        <SummaryView summary={data.summary} />
      ) : data.value ? (
        <ValueView value={data.value} />
      ) : data.schedule ? (
        <ScheduleView schedule={data.schedule} />
      ) : data.content ? (
        <ContentView content={data.content} />
      ) : (
        <FreeText text={data.answer} />
      )}
      {data.sources.length > 0 ? (
        <div>
          <h3 className="text-xs font-medium text-zinc-500">출처</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {data.sources.map((s) => (
              <li key={s.gid}>
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                  {s.title} ↗
                </a>
                <span className="ml-2 text-xs text-zinc-500">{formatDateTime(s.publishedAt)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {showLatest ? (
        <p className="text-xs text-zinc-500">
          최신 업데이트 기준:{" "}
          <a href={latest.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
            {latest.title}
          </a>{" "}
          ({formatDateTime(latest.publishedAt)})
        </p>
      ) : null}
    </div>
  );
}

function SummaryView({ summary }: { summary: NonNullable<AskResponse["summary"]> }) {
  const sections: [string, string[]][] = [
    ["새 기능", summary.newFeatures],
    ["밸런스 조정", summary.balance],
    ["버그 수정", summary.bugFixes],
  ];
  return (
    <div className="space-y-2 text-sm">
      <p className="flex flex-wrap items-center gap-2 font-medium">
        {summary.version}
        {summary.date ? <span className="text-zinc-500">({readableDate(summary.date)})</span> : null}
        <Badge>{SCALE_LABEL[summary.scale]}</Badge>
        {summary.build === "TEST" ? <Badge tone="warn">테스트 빌드</Badge> : null}
      </p>
      {sections
        .filter(([, items]) => items.length > 0)
        .map(([label, items]) => (
          <div key={label}>
            <h4 className="text-xs font-medium text-zinc-500">{label}</h4>
            <ul className="list-disc pl-5">
              {items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
    </div>
  );
}

type Value = NonNullable<AskResponse["value"]>;

// 서버가 질문 꼴로 고른 계산 방식. 큰 숫자 옆에 무엇을 계산한 값인지 붙인다
const VALUE_KIND_LABEL: Record<Value["kind"], string> = {
  CURRENT: "지금 값",
  AT_VERSION: "그 버전의 값",
  FIRST: "처음 값",
  WHEN: "바뀐 버전",
  COUNT: "바뀐 횟수",
  DIFF: "처음 대비 차이",
  VERSIONS: "바뀐 버전 목록",
};

function ValueView({ value }: { value: Value }) {
  const single = value.kind === "CURRENT" || value.kind === "AT_VERSION" || value.kind === "FIRST";
  return (
    <div className="space-y-2 text-sm">
      <div>
        <p className="text-xs text-zinc-500">
          {value.target ? `${value.target} · ` : null}
          {VALUE_KIND_LABEL[value.kind]}
        </p>
        <p className="text-lg font-semibold">
          {value.value}
          {value.kind === "COUNT" ? "번" : null}
        </p>
        {single && (value.changedIn || value.previous) ? (
          <p className="text-xs text-zinc-500">
            {value.previous ? `${value.previous} → ${value.value}` : null}
            {value.previous && value.changedIn ? " · " : null}
            {value.changedIn ? `${value.changedIn}에 바뀜` : null}
          </p>
        ) : null}
      </div>
      {value.history.length > 0 ? (
        // 모델이 공지에서 옮긴 변경 기록(서버가 날짜순으로 정렬). 위 답은 이 기록으로 서버가 계산했다
        <table className="w-full text-xs text-zinc-600 dark:text-zinc-400">
          <caption className="text-left font-medium text-zinc-500">변경 기록</caption>
          <tbody>
            {value.history.map((h) => (
              <tr key={`${h.date}-${h.version}-${h.before}-${h.after}`} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="py-1 pr-2">{h.version || "-"}</td>
                <td className="py-1 pr-2">{readableDate(h.date)}</td>
                <td className="py-1">{h.before ? `${h.before} → ${h.after}` : `${h.after} (추가)`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

type Status = NonNullable<AskResponse["content"]>["status"];
type Summary = NonNullable<AskResponse["summary"]>;
type ScheduleItem = NonNullable<AskResponse["schedule"]>["items"][number];

const SCALE_LABEL: Record<Summary["scale"], string> = { MAJOR: "대형 업데이트", PATCH: "패치", HOTFIX: "핫픽스" };
const KIND_LABEL: Record<ScheduleItem["kind"], string> = {
  EVENT: "이벤트",
  RELEASE: "출시",
  MAINTENANCE: "점검",
  TEST: "테스트",
  SALE: "할인",
};
const FORM_LABEL: Record<NonNullable<AskResponse["content"]>["form"], string> = {
  FREE_UPDATE: "무료 업데이트",
  DLC: "DLC",
  EXPANSION: "확장",
  OTHER: "콘텐츠",
};
// 상태는 서버가 오늘(한국 날짜)과 비교해 정한다. 출시는 "종료" 대신 "출시됨"으로 읽는다
const STATUS_LABEL: Record<Status, string> = { ONGOING: "진행 중", UPCOMING: "예정", ENDED: "종료", UNKNOWN: "" };

function statusLabel(status: Status, release: boolean): string {
  if (release && status === "ENDED") return "출시됨";
  if (release && status === "UPCOMING") return "출시 예정";
  if (release && status === "ONGOING") return "오늘 출시";
  return STATUS_LABEL[status];
}

function Badge({ children, tone = "plain" }: { children: React.ReactNode; tone?: "plain" | "live" | "warn" | "muted" }) {
  const tones = {
    plain: "border-zinc-300 text-zinc-600 dark:border-zinc-700 dark:text-zinc-400",
    live: "border-emerald-600 text-emerald-700 dark:border-emerald-500 dark:text-emerald-400",
    warn: "border-amber-600 text-amber-700 dark:border-amber-500 dark:text-amber-400",
    muted: "border-zinc-200 text-zinc-400 dark:border-zinc-800 dark:text-zinc-500",
  };
  return <span className={`rounded-full border px-2 py-0.5 text-xs font-normal ${tones[tone]}`}>{children}</span>;
}

function StatusBadge({ status, release }: { status: Status; release: boolean }) {
  const label = statusLabel(status, release);
  if (!label) return null;
  const tone = status === "ONGOING" ? "live" : status === "UPCOMING" ? "warn" : "muted";
  return <Badge tone={tone}>{label}</Badge>;
}

function period(start: string, end: string, singleDay: boolean): string {
  if (start && end) return `${readableDate(start)} ~ ${readableDate(end)}`;
  if (end) return `${readableDate(end)}까지`;
  // 출시일·점검은 하루짜리, 이벤트처럼 기간이 있는 일정은 시작일만 알려진 것(서버 SINGLE_DAY_KINDS와 같게)
  return singleDay ? readableDate(start) : `${readableDate(start)}부터`;
}

function ScheduleView({ schedule }: { schedule: NonNullable<AskResponse["schedule"]> }) {
  return (
    <div className="space-y-2 text-sm">
      {schedule.noCurrent ? (
        <p className="text-zinc-500">진행 중이거나 예정된 일정을 공지에서 찾지 못했습니다. 최근 끝난 일정:</p>
      ) : null}
      <ul className="space-y-2">
      {schedule.items.map((item) => (
        <li key={`${item.name}-${item.start}-${item.end}`} className={item.status === "ENDED" ? "opacity-60" : ""}>
          <p className="flex flex-wrap items-center gap-2 font-medium">
            {item.name}
            <Badge>{KIND_LABEL[item.kind]}</Badge>
            <StatusBadge status={item.status} release={item.kind === "RELEASE"} />
          </p>
          <p className="text-zinc-600 dark:text-zinc-400">
            {period(item.start, item.end, item.kind === "RELEASE" || item.kind === "MAINTENANCE")}
          </p>
        </li>
      ))}
      </ul>
    </div>
  );
}

function ContentView({ content }: { content: NonNullable<AskResponse["content"]> }) {
  return (
    <div className="space-y-1 text-sm">
      <p className="flex flex-wrap items-center gap-2 font-medium">
        {content.name}
        <Badge>{FORM_LABEL[content.form]}</Badge>
        <StatusBadge status={content.status} release />
      </p>
      {content.releaseDate ? (
        <p className="text-xs text-zinc-500">출시일 {readableDate(content.releaseDate)}</p>
      ) : null}
      {content.highlights.length > 0 ? (
        <ul className="list-disc pl-5">
          {content.highlights.map((h) => (
            <li key={h}>{h}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function FreeText({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.split("\n").length > COLLAPSE_LINES || text.length > 400;
  return (
    <div className="text-sm">
      <p className={`whitespace-pre-wrap ${long && !open ? "line-clamp-6" : ""}`}>{text}</p>
      {long ? (
        <button type="button" onClick={() => setOpen(!open)} className="mt-1 text-xs text-zinc-500 hover:underline">
          {open ? "접기" : "더 보기"}
        </button>
      ) : null}
    </div>
  );
}
