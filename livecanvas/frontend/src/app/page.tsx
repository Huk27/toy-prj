import { LiveCanvasPlayground } from "@/components/livecanvas-playground";

export default function Home() {
  return (
    <main className="min-h-screen bg-[linear-gradient(160deg,#fff7ed_0%,#fff1f2_35%,#eef2ff_100%)] px-6 py-10 text-neutral-950">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-10">
        <header className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-orange-600">
            LiveCanvas
          </p>
          <div className="max-w-3xl space-y-3">
            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-6xl">
              Next.js playground for your WebFlux WebSocket server
            </h1>
            <p className="text-base leading-7 text-neutral-700 sm:text-lg">
              프론트 초반 단계에서는 먼저 연결, 메시지 전송, 에러 응답 흐름을 눈으로
              확인하는 것이 중요합니다. 이 화면은 그 학습용 최소 클라이언트입니다.
            </p>
          </div>
        </header>

        <LiveCanvasPlayground />
      </div>
    </main>
  );
}
