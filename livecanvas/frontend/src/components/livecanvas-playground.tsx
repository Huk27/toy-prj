"use client";

import { useEffect, useRef, useState } from "react";

type ConnectionState = "disconnected" | "connecting" | "connected" | "error";

type ReceivedMessage = {
  id: number;
  text: string;
};

type StrokePayload = {
  strokeId: string;
  x: number;
  y: number;
  color: string;
  width: number;
};

type ClientMessage =
  | {
      type: "WELCOME";
      payload: {
        userId: string;
        sessionId: string;
        channelId: string;
      };
    }
  | {
      type: "STROKE";
      payload: StrokePayload;
    }
  | {
      type: "ERROR";
      payload: {
        message: string;
      };
    };

const DEFAULT_USER_ID = "user-a";
const DEFAULT_CHANNEL_ID = "room-1";
const DEFAULT_SOCKET_URL = "ws://localhost:8080/ws/canvas";
const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 600;
const DEFAULT_COLOR = "#ff5a36";
const DEFAULT_BRUSH_SIZE = 6;

export function LiveCanvasPlayground() {
  const socketRef = useRef<WebSocket | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const strokesRef = useRef<StrokePayload[]>([]);
  const isDrawingRef = useRef(false);
  const messageIdRef = useRef(1);

  const [socketUrl, setSocketUrl] = useState(DEFAULT_SOCKET_URL);
  const [userId, setUserId] = useState(DEFAULT_USER_ID);
  const [channelId, setChannelId] = useState(DEFAULT_CHANNEL_ID);
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("disconnected");
  const [messages, setMessages] = useState<ReceivedMessage[]>([]);
  const [brushColor, setBrushColor] = useState(DEFAULT_COLOR);
  const [brushSize, setBrushSize] = useState(DEFAULT_BRUSH_SIZE);
  const [strokeCount, setStrokeCount] = useState(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    canvas.width = CANVAS_WIDTH;
    canvas.height = CANVAS_HEIGHT;
    redrawCanvas();

    return () => {
      socketRef.current?.close();
    };
  }, []);

  function pushMessage(text: string) {
    setMessages((current) => [
      {
        id: messageIdRef.current++,
        text,
      },
      ...current,
    ]);
  }

  function getContext() {
    const canvas = canvasRef.current;
    if (!canvas) {
      return null;
    }
    return canvas.getContext("2d");
  }

  function redrawCanvas() {
    const context = getContext();
    if (!context) {
      return;
    }

    context.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    context.fillStyle = "#fffdf8";
    context.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

    context.save();
    context.strokeStyle = "rgba(234, 88, 12, 0.08)";
    context.lineWidth = 1;

    for (let x = 24; x < CANVAS_WIDTH; x += 24) {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, CANVAS_HEIGHT);
      context.stroke();
    }

    for (let y = 24; y < CANVAS_HEIGHT; y += 24) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(CANVAS_WIDTH, y);
      context.stroke();
    }

    context.restore();

    for (const stroke of strokesRef.current) {
      drawStroke(stroke);
    }
  }

  function drawStroke(stroke: StrokePayload) {
    const context = getContext();
    if (!context) {
      return;
    }

    context.beginPath();
    context.fillStyle = stroke.color;
    context.arc(stroke.x, stroke.y, stroke.width / 2, 0, Math.PI * 2);
    context.fill();
  }

  function appendStroke(stroke: StrokePayload) {
    strokesRef.current = [...strokesRef.current, stroke];
    setStrokeCount(strokesRef.current.length);
    drawStroke(stroke);
  }

  function resetLocalCanvas() {
    strokesRef.current = [];
    setStrokeCount(0);
    redrawCanvas();
    pushMessage("[system] local canvas reset");
  }

  function connect() {
    socketRef.current?.close();

    const url = new URL(socketUrl);
    url.searchParams.set("channelId", channelId);
    url.searchParams.set("userId", userId);

    const socket = new WebSocket(url);
    socketRef.current = socket;
    setConnectionState("connecting");

    socket.onopen = () => {
      setConnectionState("connected");
      pushMessage(`[system] connected as ${userId} in ${channelId}`);
    };

    socket.onmessage = (event) => {
      pushMessage(event.data);

      try {
        const message = JSON.parse(event.data) as ClientMessage;
        if (message.type === "STROKE") {
          appendStroke(message.payload);
        }
      } catch {
        pushMessage("[system] failed to parse message");
      }
    };

    socket.onerror = () => {
      setConnectionState("error");
      pushMessage("[system] socket error");
    };

    socket.onclose = () => {
      setConnectionState("disconnected");
      pushMessage("[system] disconnected");
    };
  }

  function disconnect() {
    socketRef.current?.close();
    socketRef.current = null;
  }

  function sendUnsupportedMessage() {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      pushMessage("[system] socket is not connected");
      return;
    }

    const message = {
      type: "PING",
      payload: {},
    };

    socket.send(JSON.stringify(message));
    pushMessage(`[sent] ${JSON.stringify(message)}`);
  }

  function sendStroke(stroke: StrokePayload) {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      pushMessage("[system] socket is not connected");
      return false;
    }

    const message = {
      type: "STROKE",
      payload: stroke,
    };

    socket.send(JSON.stringify(message));
    pushMessage(`[sent] ${JSON.stringify(message)}`);
    return true;
  }

  function buildStroke(clientX: number, clientY: number) {
    const canvas = canvasRef.current;
    if (!canvas) {
      return null;
    }

    const rect = canvas.getBoundingClientRect();
    const x = Math.round(((clientX - rect.left) / rect.width) * CANVAS_WIDTH);
    const y = Math.round(((clientY - rect.top) / rect.height) * CANVAS_HEIGHT);

    return {
      strokeId: `${userId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      x: Math.max(0, Math.min(CANVAS_WIDTH, x)),
      y: Math.max(0, Math.min(CANVAS_HEIGHT, y)),
      color: brushColor,
      width: brushSize,
    } satisfies StrokePayload;
  }

  function paint(clientX: number, clientY: number) {
    const stroke = buildStroke(clientX, clientY);
    if (!stroke) {
      return;
    }

    const sent = sendStroke(stroke);
    if (!sent) {
      return;
    }

    appendStroke(stroke);
  }

  function handlePointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    isDrawingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    paint(event.clientX, event.clientY);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!isDrawingRef.current) {
      return;
    }
    paint(event.clientX, event.clientY);
  }

  function handlePointerUp(event: React.PointerEvent<HTMLCanvasElement>) {
    isDrawingRef.current = false;
    event.currentTarget.releasePointerCapture(event.pointerId);
  }

  return (
    <section className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="space-y-5 rounded-[30px] border border-black/10 bg-white/88 p-6 shadow-[0_28px_90px_rgba(15,23,42,0.10)] backdrop-blur">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-orange-600">
            Studio
          </p>
          <h2 className="text-2xl font-semibold tracking-tight text-neutral-950">
            Collaborative drawing controls
          </h2>
          <p className="text-sm leading-6 text-neutral-600">
            두 개의 브라우저 창을 같은 channel로 연결한 뒤, 오른쪽 보드에서 바로
            드로잉을 테스트할 수 있습니다.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-2xl bg-neutral-950 px-4 py-3 text-sm text-neutral-100">
            status
            <div className="mt-1 font-semibold text-emerald-300">
              {connectionState}
            </div>
          </div>
          <div className="rounded-2xl bg-orange-500 px-4 py-3 text-sm text-white">
            strokes
            <div className="mt-1 font-semibold">{strokeCount}</div>
          </div>
        </div>

        <label className="block space-y-2 text-sm">
          <span className="font-medium text-neutral-800">Socket URL</span>
          <input
            className="w-full rounded-2xl border border-neutral-200 bg-neutral-50 px-4 py-3 outline-none transition focus:border-orange-400 focus:bg-white"
            value={socketUrl}
            onChange={(event) => setSocketUrl(event.target.value)}
          />
        </label>

        <label className="block space-y-2 text-sm">
          <span className="font-medium text-neutral-800">User ID</span>
          <input
            className="w-full rounded-2xl border border-neutral-200 bg-neutral-50 px-4 py-3 outline-none transition focus:border-orange-400 focus:bg-white"
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
          />
        </label>

        <label className="block space-y-2 text-sm">
          <span className="font-medium text-neutral-800">Channel ID</span>
          <input
            className="w-full rounded-2xl border border-neutral-200 bg-neutral-50 px-4 py-3 outline-none transition focus:border-orange-400 focus:bg-white"
            value={channelId}
            onChange={(event) => setChannelId(event.target.value)}
          />
        </label>

        <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
          <label className="space-y-2 text-sm">
            <span className="font-medium text-neutral-800">Brush color</span>
            <input
              type="color"
              value={brushColor}
              onChange={(event) => setBrushColor(event.target.value)}
              className="h-12 w-full cursor-pointer rounded-2xl border border-neutral-200 bg-neutral-50 px-2"
            />
          </label>
          <label className="space-y-2 text-sm">
            <span className="font-medium text-neutral-800">Size</span>
            <input
              type="range"
              min="2"
              max="18"
              value={brushSize}
              onChange={(event) => setBrushSize(Number(event.target.value))}
              className="mt-4 w-full accent-orange-500"
            />
            <div className="text-center text-xs font-medium text-neutral-500">
              {brushSize}px
            </div>
          </label>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <button
            className="rounded-2xl bg-neutral-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-neutral-800"
            onClick={connect}
            type="button"
          >
            Connect
          </button>
          <button
            className="rounded-2xl border border-neutral-300 px-4 py-3 text-sm font-semibold text-neutral-800 transition hover:bg-neutral-50"
            onClick={disconnect}
            type="button"
          >
            Disconnect
          </button>
          <button
            className="rounded-2xl border border-orange-300 px-4 py-3 text-sm font-semibold text-orange-700 transition hover:bg-orange-50"
            onClick={sendUnsupportedMessage}
            type="button"
          >
            Send PING
          </button>
          <button
            className="rounded-2xl border border-neutral-300 px-4 py-3 text-sm font-semibold text-neutral-800 transition hover:bg-neutral-50"
            onClick={resetLocalCanvas}
            type="button"
          >
            Reset local view
          </button>
        </div>

        <div className="rounded-3xl border border-neutral-200 bg-neutral-50 p-4 text-sm leading-6 text-neutral-600">
          연결 후 오른쪽 보드에서 드래그하면 로컬 캔버스에 즉시 그려지고,
          같은 채널의 다른 브라우저에도 반영됩니다. `PING` 버튼은 unsupported
          type에 대한 개인 `ERROR` 응답을 테스트하기 위한 것입니다.
        </div>
      </aside>

      <div className="grid gap-6">
        <div className="overflow-hidden rounded-[30px] border border-black/10 bg-white/72 shadow-[0_30px_100px_rgba(15,23,42,0.12)]">
          <div className="flex items-center justify-between border-b border-black/8 px-6 py-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-orange-600">
                Canvas
              </p>
              <h3 className="mt-2 text-lg font-semibold text-neutral-950">
                Channel {channelId}
              </h3>
            </div>
            <div className="rounded-full bg-neutral-950 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-white">
              {userId}
            </div>
          </div>

          <div className="p-4 sm:p-6">
            <div className="overflow-hidden rounded-[28px] border border-orange-200 bg-[linear-gradient(180deg,#fffef8,#fff8ef)]">
              <canvas
                ref={canvasRef}
                width={CANVAS_WIDTH}
                height={CANVAS_HEIGHT}
                className="block aspect-[16/10] w-full touch-none cursor-crosshair bg-transparent"
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerLeave={handlePointerUp}
              />
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-[30px] border border-black/10 bg-neutral-950 shadow-[0_28px_90px_rgba(15,23,42,0.14)]">
          <div className="border-b border-white/10 px-6 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-orange-300">
              Event Log
            </p>
            <p className="mt-2 text-sm text-neutral-300">
              `WELCOME`, broadcast된 `STROKE`, 개인 `ERROR` 메시지를 여기서
              확인합니다.
            </p>
          </div>

          <div className="flex min-h-[240px] flex-col gap-3 bg-[radial-gradient(circle_at_top,#2a2a2a,transparent_40%),linear-gradient(180deg,#171717,#0a0a0a)] p-5">
            {messages.length === 0 ? (
              <div className="flex flex-1 items-center justify-center rounded-3xl border border-dashed border-white/15 text-sm text-neutral-500">
                아직 수신된 메시지가 없습니다.
              </div>
            ) : (
              messages.map((message) => (
                <pre
                  key={message.id}
                  className="overflow-x-auto rounded-2xl border border-white/8 bg-white/5 px-4 py-3 text-xs leading-6 text-neutral-200"
                >
                  {message.text}
                </pre>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
