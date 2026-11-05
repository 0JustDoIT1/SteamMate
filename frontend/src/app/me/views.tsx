"use client";

import LibraryGate, { GameList, GenreDistribution, LibraryStats } from "./my-library";
import MyDeals from "./my-deals";
import OwnedRecommendations from "./my-recommendations";
import StoreRecommendationsPanel from "./my-store-recommendations";

/*
 * 사이드바 메뉴마다 한 페이지(사용자 요청: 탭 대신 메뉴로 분리). 모두 로그인·라이브러리 확인(LibraryGate)을 거친다.
 * 라이브러리 응답은 React Query 캐시를 함께 써서 페이지를 옮겨도 다시 받지 않는다.
 */

export function LibraryHomeView() {
  return (
    <LibraryGate>
      {(library) => (
        <>
          <LibraryStats library={library} />
          {library.gameCount === 0 ? <p className="text-zinc-500">보유한 게임이 없습니다.</p> : <OwnedRecommendations />}
        </>
      )}
    </LibraryGate>
  );
}

export function StoreView() {
  return <LibraryGate>{() => <StoreRecommendationsPanel />}</LibraryGate>;
}

export function DealsView() {
  return <LibraryGate>{() => <MyDeals />}</LibraryGate>;
}

export function GenresView() {
  return <LibraryGate>{(library) => <GenreDistribution library={library} />}</LibraryGate>;
}

export function OwnedGamesView() {
  return (
    <LibraryGate>
      {(library) =>
        library.gameCount === 0 ? <p className="text-zinc-500">보유한 게임이 없습니다.</p> : <GameList library={library} />
      }
    </LibraryGate>
  );
}
