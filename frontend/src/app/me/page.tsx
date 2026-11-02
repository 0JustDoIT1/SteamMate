import MyLibrary from "./my-library";

export default function MePage() {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">내 라이브러리</h1>
      <MyLibrary />
    </main>
  );
}
