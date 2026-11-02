"use client";

import { STEAM_LOGIN_URL, useMe } from "@/features/auth/queries";
import { type Library, useMyLibrary } from "@/features/library/queries";
import { ApiError } from "@/lib/api/client";
import { useHydrated } from "@/lib/use-hydrated";

const PRIVACY_SETTINGS_URL = "https://steamcommunity.com/my/edit/settings";

function hours(minutes: number) {
  return minutes < 60 ? `${minutes}분` : `${(minutes / 60).toFixed(1)}시간`;
}

export default function MyLibrary() {
  const hydrated = useHydrated();
  const { data: me, isPending: mePending } = useMe();
  const library = useMyLibrary(Boolean(me));

  if (!hydrated || mePending) return <p className="mt-6 text-zinc-500">확인 중…</p>;

  if (!me) {
    return (
      <div className="mt-6 space-y-3">
        <p>내 라이브러리를 보려면 Steam 로그인이 필요합니다.</p>
        <a href={STEAM_LOGIN_URL} className="inline-block rounded-md bg-zinc-900 px-4 py-2 text-white dark:bg-zinc-100 dark:text-zinc-900">
          Steam으로 로그인
        </a>
      </div>
    );
  }

  if (library.isPending) return <p className="mt-6 text-zinc-500">Steam에서 라이브러리를 불러오는 중…</p>;
  if (library.isError) return <LibraryError error={library.error} onRetry={() => library.refetch()} />;

  return <LibraryView library={library.data} />;
}

function LibraryError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const code = error instanceof ApiError ? error.code : "UNKNOWN_ERROR";

  if (code === "LIBRARY_PRIVATE") {
    return (
      <div className="mt-6 space-y-3 rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
        <p className="font-medium">게임 목록을 볼 수 없습니다.</p>
        <p className="text-sm">{error.message.replace(` (${PRIVACY_SETTINGS_URL})`, "")}</p>
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          <li>Steam 공개 설정을 엽니다.</li>
          <li>&lsquo;내 프로필&rsquo;과 &lsquo;게임 세부 정보&rsquo;를 &lsquo;공개&rsquo;로 바꿉니다.</li>
          <li>이 페이지로 돌아와 다시 불러옵니다.</li>
        </ol>
        <div className="flex gap-2">
          <a href={PRIVACY_SETTINGS_URL} target="_blank" rel="noopener noreferrer" className="rounded-md border border-amber-400 px-3 py-1.5 text-sm">
            Steam 공개 설정 열기
          </a>
          <button type="button" onClick={onRetry} className="rounded-md border border-amber-400 px-3 py-1.5 text-sm">
            다시 불러오기
          </button>
        </div>
      </div>
    );
  }

  return (
    <div role="alert" className="mt-6 space-y-2 rounded-md border border-red-300 bg-red-50 p-4 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
      <p>{error.message}</p>
      <button type="button" onClick={onRetry} className="rounded-md border border-red-400 px-3 py-1.5 text-sm">
        다시 시도
      </button>
    </div>
  );
}

function LibraryView({ library }: { library: Library }) {
  const { summary } = library;
  const stats = [
    ["보유 게임", `${library.gameCount}개`],
    ["총 플레이", hours(summary.totalPlaytimeMinutes)],
    ["플레이한 게임", `${summary.playedCount}개`],
    ["미플레이", `${summary.unplayedCount}개`],
    ["최근 2주 플레이", `${summary.recentlyPlayedCount}개`],
  ];

  return (
    <div className="mt-6 space-y-6">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {stats.map(([label, value]) => (
          <div key={label} className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
            <dt className="text-xs text-zinc-500">{label}</dt>
            <dd className="mt-1 text-lg font-semibold">{value}</dd>
          </div>
        ))}
      </dl>

      {library.gameCount === 0 ? (
        <p className="text-zinc-500">보유한 게임이 없습니다.</p>
      ) : (
        <ul className="divide-y divide-zinc-200 rounded-md border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
          {library.games.map((game) => (
            <li key={game.appid} className="flex items-center gap-3 px-3 py-2">
              {game.iconUrl ? (
                // Steam CDN 아이콘(32px). next/image 원격 도메인 설정 없이 그대로 표시한다.
                // eslint-disable-next-line @next/next/no-img-element
                <img src={game.iconUrl} alt="" width={32} height={32} className="rounded" />
              ) : (
                <span className="h-8 w-8 rounded bg-zinc-200 dark:bg-zinc-800" />
              )}
              <span className="flex-1 truncate">{game.name}</span>
              {game.playtime2Weeks > 0 && (
                <span className="text-xs text-emerald-600">최근 {hours(game.playtime2Weeks)}</span>
              )}
              <span className="w-20 text-right text-sm tabular-nums text-zinc-600 dark:text-zinc-400">
                {game.playtimeForever > 0 ? hours(game.playtimeForever) : "미플레이"}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-zinc-500">
        조회 시각 {new Date(library.fetchedAt).toLocaleString("ko-KR")} · 라이브러리는 저장하지 않으며 요청할 때마다
        Steam에서 조회합니다.
      </p>
    </div>
  );
}
