import { Stack } from "expo-router";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { ThemeProvider } from "@/providers/theme-provider";
import { AppProvider } from "@/providers/app-provider";
import { AppShell } from "@/components/ui/app-shell";

export default function Layout() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <AppProvider>
          <AppShell>
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: "transparent" },
              }}
            />
          </AppShell>
        </AppProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
