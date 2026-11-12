import {
  createContext,
  type PropsWithChildren,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  ActivityRepository,
  openRepository,
  type Snapshot,
} from "@/infrastructure/storage/repository";
import { cleanupExportCache } from "@/infrastructure/transfer/export-cache";
import { isQaBuild } from "@/infrastructure/runtime";
import { buildDemoData } from "@/features/qa/demo-data";

type Value = Snapshot & {
  loading: boolean;
  busy: boolean;
  error: string | null;
  retry: () => void;
  clearError: () => void;
  mutate: <T>(action: (repo: ActivityRepository) => Promise<T>) => Promise<T>;
};
const Context = createContext<Value | null>(null);
export function AppProvider({ children }: PropsWithChildren) {
  const [snapshot, setSnapshot] = useState<Snapshot>({
    activities: [],
    calibrations: [],
  });
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [attempt, setAttempt] = useState(0);
  const repository = useRef<ActivityRepository | null>(null),
    locked = useRef(false);
  useEffect(() => {
    let active = true;
    openRepository(isQaBuild)
      .then(async (repo) => {
        try {
          cleanupExportCache();
        } catch {
          /* Cache cleanup must not hide an otherwise healthy library. */
        }
        if (isQaBuild) {
          const demo = buildDemoData();
          await repo.loadDemoLibrary(demo.activities, demo.calibrations, true);
        }
        const next = await repo.snapshot();
        if (active) {
          repository.current = repo;
          setSnapshot(next);
        }
      })
      .catch((e) => {
        if (active)
          setError(
            e instanceof Error ? e.message : "Could not open local storage.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  async function mutate<T>(
    action: (repo: ActivityRepository) => Promise<T>,
  ): Promise<T> {
    if (!repository.current) throw new Error("Local storage is not ready.");
    if (locked.current) throw new Error("An operation is already in progress.");
    locked.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await action(repository.current);
      setSnapshot(await repository.current.snapshot());
      return result;
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not complete the operation.",
      );
      throw e;
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  return (
    <Context.Provider
      value={{
        ...snapshot,
        loading,
        busy,
        error,
        mutate,
        retry: () => {
          setLoading(true);
          setError(null);
          setAttempt((n) => n + 1);
        },
        clearError: () => setError(null),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useApp() {
  const value = useContext(Context);
  if (!value) throw new Error("AppProvider is missing.");
  return value;
}
