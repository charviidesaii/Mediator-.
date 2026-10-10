import { useEffect, useState } from "react";
import { apiClient } from "./client";
import type { ResourceState } from "./models";

export function useApiResource<T>(path: string | null, demoData?: T) {
  const [state, setState] = useState<ResourceState<T>>(
    demoData === undefined
      ? { status: "idle" }
      : { status: "demo", data: demoData },
  );

  useEffect(() => {
    if (!path) {
      setState(demoData === undefined
        ? { status: "idle" }
        : { status: "demo", data: demoData });
      return;
    }

    let active = true;
    setState({ status: "loading" });

    apiClient.request<T>(path)
      .then((data) => {
        if (active) setState({ status: "success", data });
      })
      .catch((error: unknown) => {
        if (!active) return;
        const normalizedError = error instanceof Error ? error : new Error("Unable to load data.");
        setState(demoData === undefined
          ? { status: "error", error: normalizedError }
          : { status: "demo", data: demoData, error: normalizedError });
      });

    return () => {
      active = false;
    };
  }, [path, demoData]);

  return state;
}
