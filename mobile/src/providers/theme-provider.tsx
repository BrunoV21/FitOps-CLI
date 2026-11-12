import {
  createContext,
  type PropsWithChildren,
  useContext,
  useEffect,
  useState,
} from "react";
import { useColorScheme } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import tokens from "@/theme/tokens.json";

export type ThemePreference = "system" | "dark" | "light";
type ThemeValue = {
  mode: "dark" | "light";
  colors: typeof tokens.colors.dark;
  preference: ThemePreference;
  setPreference: (p: ThemePreference) => Promise<void>;
};
const Context = createContext<ThemeValue | null>(null);
// Adapted from BranchBalance's theme context; see THIRD_PARTY_NOTICES.md.
export function ThemeProvider({ children }: PropsWithChildren) {
  const system = useColorScheme();
  const [preference, setValue] = useState<ThemePreference>("system");
  useEffect(() => {
    let active = true;
    AsyncStorage.getItem("fitops.appearance")
      .then((v) => {
        if (active && (v === "dark" || v === "light")) setValue(v);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  const mode =
    preference === "system"
      ? system === "light"
        ? "light"
        : "dark"
      : preference;
  async function setPreference(next: ThemePreference) {
    await AsyncStorage.setItem("fitops.appearance", next);
    setValue(next);
  }
  return (
    <Context.Provider
      value={{ mode, colors: tokens.colors[mode], preference, setPreference }}
    >
      {children}
    </Context.Provider>
  );
}
export function useTheme() {
  const value = useContext(Context);
  if (!value) throw new Error("ThemeProvider is missing.");
  return value;
}
