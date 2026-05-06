import type { ApiAppHealthPayload } from "./types";

const APP_HEALTH_CHANNEL_NAME = "finops.appHealth";
const APP_HEALTH_SNAPSHOT_MESSAGE = "app-health:snapshot";

export type AppHealthBroadcastMessage = {
  type: typeof APP_HEALTH_SNAPSHOT_MESSAGE;
  generatedAt: string;
  payload: ApiAppHealthPayload;
};

export type AppHealthBroadcast = {
  publish: (payload: ApiAppHealthPayload, generatedAt?: string) => void;
  close: () => void;
};

export function getAppHealthSnapshotGeneratedAt(payload: ApiAppHealthPayload): string {
  const generatedAt = typeof payload.generated_at === "string" ? payload.generated_at.trim() : "";
  return generatedAt || new Date().toISOString();
}

export function isAppHealthSnapshotFresh(incomingGeneratedAt: string, currentGeneratedAt: string | null) {
  if (!currentGeneratedAt) {
    return true;
  }
  const incomingTime = Date.parse(incomingGeneratedAt);
  const currentTime = Date.parse(currentGeneratedAt);
  if (Number.isNaN(incomingTime)) {
    return false;
  }
  if (Number.isNaN(currentTime)) {
    return true;
  }
  return incomingTime >= currentTime;
}

function isAppHealthBroadcastMessage(data: unknown): data is AppHealthBroadcastMessage {
  if (!data || typeof data !== "object") {
    return false;
  }
  const message = data as Partial<AppHealthBroadcastMessage>;
  return (
    message.type === APP_HEALTH_SNAPSHOT_MESSAGE
    && typeof message.generatedAt === "string"
    && !!message.payload
    && typeof message.payload === "object"
  );
}

export function createAppHealthBroadcast(
  onSnapshot: (message: AppHealthBroadcastMessage) => void,
): AppHealthBroadcast | null {
  if (typeof globalThis.BroadcastChannel !== "function") {
    return null;
  }

  let channel: BroadcastChannel;
  try {
    channel = new BroadcastChannel(APP_HEALTH_CHANNEL_NAME);
  } catch {
    return null;
  }

  channel.onmessage = (event) => {
    if (isAppHealthBroadcastMessage(event.data)) {
      onSnapshot(event.data);
    }
  };

  return {
    publish: (payload, generatedAt = getAppHealthSnapshotGeneratedAt(payload)) => {
      try {
        channel.postMessage({
          type: APP_HEALTH_SNAPSHOT_MESSAGE,
          generatedAt,
          payload,
        } satisfies AppHealthBroadcastMessage);
      } catch {
        // BroadcastChannel is an optimization; local health updates remain authoritative.
      }
    },
    close: () => {
      channel.close();
    },
  };
}
