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
  return (
    <div className="space-y-3 border-t border-zinc-200 px-4 py-4 dark:border-zinc-800">
      {data.refused ? (
        <p className="text-sm text-zinc-500">공지에서 근거를 찾지 못했습니다. ({data.answer})</p>
      ) : data.summary ? (
        <SummaryView summary={data.summary} />
      ) : data.value ? (
        <ValueView value={data.value} />
      ) : data.schedule ? (
        <ScheduleView schedule={data.schedule} />
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
      {data.latestUpdate ? (
        <p className="text-xs text-zinc-500">
          최신 업데이트 기준:{" "}
          <a href={data.latestUpdate.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
            {data.latestUpdate.title}
          </a>{" "}
          ({formatDateTime(data.latestUpdate.publishedAt)})
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
      {summary.version || summary.date ? (
        <p className="font-medium">
          {summary.version} {summary.date ? <span className="text-zinc-500">({summary.date})</span> : null}
        </p>
      ) : null}
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

function ValueView({ value }: { value: NonNullable<AskResponse["value"]> }) {
  return (
    <div className="text-sm">
      {value.target ? <p className="text-xs text-zinc-500">{value.target}</p> : null}
      <p className="text-lg font-semibold">{value.value}</p>
      {value.changedIn || value.previous ? (
        <p className="text-xs text-zinc-500">
          {value.previous ? `${value.previous} → ${value.value}` : null}
          {value.previous && value.changedIn ? " · " : null}
          {value.changedIn ? `${value.changedIn}에 바뀜` : null}
        </p>
      ) : null}
    </div>
  );
}

function ScheduleView({ schedule }: { schedule: NonNullable<AskResponse["schedule"]> }) {
  return (
    <div className="text-sm">
      <p className="font-medium">{schedule.name}</p>
      <p className="text-zinc-600 dark:text-zinc-400">
        {schedule.start && schedule.end
          ? `${readableDate(schedule.start)} ~ ${readableDate(schedule.end)}`
          : schedule.end
            ? `${readableDate(schedule.end)}까지`
            : readableDate(schedule.start)}
      </p>
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
