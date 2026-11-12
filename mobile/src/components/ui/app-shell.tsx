import { useEffect, useState, type PropsWithChildren } from "react";
import {
  AccessibilityInfo,
  Animated,
  BackHandler,
  Modal,
  Pressable,
  Text,
  View,
} from "react-native";
import { usePathname, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { StatusBar } from "expo-status-bar";
import { useTheme } from "@/providers/theme-provider";
import { useApp } from "@/providers/app-provider";
import { Body, Button, Notice } from "./index";
import { isQaBuild } from "@/infrastructure/runtime";
import { useKeepAwake } from "expo-keep-awake";

function QaScreenAwake() {
  useKeepAwake("fitops-qa");
  return null;
}

const destinations = [
  { path: "/" as const, label: "Overview" },
  { path: "/activities" as const, label: "Activities" },
  { path: "/zones" as const, label: "HR zones" },
  { path: "/settings" as const, label: "Settings" },
  ...(isQaBuild ? [{ path: "/qa" as const, label: "QA library" }] : []),
];
export function AppShell({ children }: PropsWithChildren) {
  const { colors, mode } = useTheme(),
    { busy, loading, error, retry, clearError, activities } = useApp();
  const pathname = usePathname(),
    router = useRouter();
  const [open, setOpen] = useState(false),
    [reduce, setReduce] = useState(false);
  const [progress] = useState(() => new Animated.Value(0));
  const current =
    destinations.find((d) =>
      d.path === "/" ? pathname === "/" : pathname.startsWith(d.path),
    )?.label ?? "Activity";
  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduce);
    const event = AccessibilityInfo.addEventListener(
      "reduceMotionChanged",
      setReduce,
    );
    return () => event.remove();
  }, []);
  useEffect(() => {
    if (open) {
      progress.setValue(0);
      Animated.timing(progress, {
        toValue: 1,
        duration: reduce ? 0 : 180,
        useNativeDriver: true,
      }).start();
    }
  }, [open, progress, reduce]);
  useEffect(() => {
    const event = BackHandler.addEventListener("hardwareBackPress", () => {
      if (pathname !== "/" && !router.canGoBack()) {
        router.replace("/");
        return true;
      }
      return false;
    });
    return () => event.remove();
  }, [pathname, router]);
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}>
      {isQaBuild ? <QaScreenAwake /> : null}
      <StatusBar style={mode === "dark" ? "light" : "dark"} />
      <View style={{ paddingHorizontal: 20, paddingTop: 8, paddingBottom: 4 }}>
        <LinearGradient
          colors={
            mode === "dark" ? ["#29372f", "#131c17"] : ["#ffffff", "#e5f0e8"]
          }
          style={{
            borderWidth: 1,
            borderColor: colors.border,
            borderRadius: 16,
            padding: 8,
            paddingLeft: 18,
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="FitOps overview"
            onPress={() => router.replace("/")}
            style={{ minHeight: 48, justifyContent: "center" }}
          >
            <Text
              style={{
                fontFamily: "monospace",
                fontSize: 14,
                fontWeight: "800",
                letterSpacing: 1,
                color: colors.text,
              }}
            >
              <Text style={{ color: colors.positive }}>△ </Text>FITOPS
            </Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Navigation, ${current}`}
            accessibilityState={{ expanded: open }}
            onPress={() => setOpen(true)}
            style={{
              minHeight: 48,
              padding: 12,
              borderWidth: 1,
              borderColor: colors.border,
              borderRadius: 8,
              backgroundColor: colors.surfaceStrong,
            }}
          >
            <Body size={14}>{current} ≡</Body>
          </Pressable>
        </LinearGradient>
      </View>
      {isQaBuild ? (
        <View style={{ paddingHorizontal: 24, paddingTop: 4 }}>
          <Text
            style={{
              fontFamily: "monospace",
              fontSize: 11,
              color: colors.positive,
              letterSpacing: 1,
            }}
          >
            {activities.some(
              (a) => a.activity.provider_account_id === "fitops-demo",
            )
              ? "QA · DEMO DATA"
              : "QA BUILD"}
          </Text>
        </View>
      ) : null}
      {busy ? (
        <View
          accessibilityLiveRegion="polite"
          style={{ paddingHorizontal: 20, paddingVertical: 4 }}
        >
          <Body muted size={13}>
            Saving locally…
          </Body>
        </View>
      ) : null}
      {error ? (
        <View style={{ paddingHorizontal: 20, paddingTop: 8, gap: 8 }}>
          <Notice>{error}</Notice>
          <Button
            disabled={busy}
            onPress={() => {
              clearError();
              retry();
            }}
          >
            Reload local data
          </Button>
        </View>
      ) : null}
      {loading ? (
        <View style={{ padding: 24 }}>
          <Body>Opening your local library…</Body>
        </View>
      ) : (
        children
      )}
      <Modal
        visible={open}
        transparent
        animationType="none"
        onRequestClose={() => setOpen(false)}
      >
        <SafeAreaView style={{ flex: 1 }}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close navigation"
            onPress={() => setOpen(false)}
            style={{
              position: "absolute",
              inset: 0,
              backgroundColor: "rgba(0,0,0,.35)",
            }}
          />
          <Animated.View
            accessibilityViewIsModal
            style={{
              alignSelf: "flex-end",
              width: "85%",
              maxWidth: 340,
              marginTop: 16,
              marginRight: 20,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.surfaceStrong,
              padding: 12,
              gap: 6,
              opacity: progress,
              transform: [
                {
                  translateY: progress.interpolate({
                    inputRange: [0, 1],
                    outputRange: [-8, 0],
                  }),
                },
              ],
            }}
          >
            {destinations.map((d, i) => (
              <Pressable
                key={d.path}
                accessibilityRole="button"
                accessibilityState={{ selected: current === d.label }}
                onPress={() => {
                  setOpen(false);
                  router.replace(d.path);
                }}
                style={{
                  minHeight: 52,
                  padding: 14,
                  borderRadius: 8,
                  backgroundColor:
                    current === d.label ? colors.surface : colors.surfaceStrong,
                  flexDirection: "row",
                  justifyContent: "space-between",
                }}
              >
                <Text
                  style={{
                    fontFamily: "monospace",
                    color: current === d.label ? colors.positive : colors.text,
                    fontSize: 16,
                  }}
                >
                  {d.label}
                </Text>
                <Body muted size={13}>
                  0{i + 1}
                </Body>
              </Pressable>
            ))}
            <Button onPress={() => setOpen(false)}>Close</Button>
          </Animated.View>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}
