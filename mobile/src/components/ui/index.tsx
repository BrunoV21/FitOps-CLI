import { useState, type PropsWithChildren, type ReactNode } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";
import { useTheme } from "@/providers/theme-provider";
import tokens from "@/theme/tokens.json";

export function Body({
  children,
  muted = false,
  size = 16,
}: PropsWithChildren<{ muted?: boolean; size?: number }>) {
  const { colors } = useTheme();
  return (
    <Text
      selectable
      style={{
        color: muted ? colors.muted : colors.text,
        fontFamily: "monospace",
        fontSize: size,
        lineHeight: size * 1.5,
      }}
    >
      {children}
    </Text>
  );
}
export function Title({ children }: PropsWithChildren) {
  const { colors } = useTheme();
  return (
    <Text
      accessibilityRole="header"
      style={{
        color: colors.text,
        fontFamily: "monospace",
        fontSize: 28,
        fontWeight: "700",
        marginBottom: 8,
      }}
    >
      {children}
    </Text>
  );
}
export function Card({
  children,
  label,
}: PropsWithChildren<{ label?: string }>) {
  const { colors } = useTheme();
  return (
    <View
      style={{
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
        borderRadius: tokens.shape.radius,
        padding: 20,
        gap: 10,
      }}
    >
      {label ? (
        <Text
          accessibilityRole="header"
          style={{
            fontFamily: "monospace",
            color: colors.positive,
            fontSize: 13,
            fontWeight: "700",
          }}
        >
          {label.toUpperCase()}
        </Text>
      ) : null}
      {children}
    </View>
  );
}
export function MetricValue({ value, unit }: { value: string; unit?: string }) {
  const { colors } = useTheme();
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "baseline",
        flexWrap: "wrap",
        gap: 10,
      }}
    >
      <Text
        style={{
          fontFamily: "monospace",
          fontSize: 40,
          fontWeight: "700",
          color: colors.text,
        }}
      >
        {value}
      </Text>
      {unit ? (
        <Body muted size={14}>
          {unit}
        </Body>
      ) : null}
    </View>
  );
}
export function Button({
  children,
  onPress,
  variant = "secondary",
  disabled = false,
  loading = false,
}: PropsWithChildren<{
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  loading?: boolean;
}>) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || loading, busy: loading }}
      disabled={disabled || loading}
      onPress={onPress}
      style={({ pressed }) => ({
        minHeight: 48,
        padding: 12,
        borderWidth: 1,
        borderColor: variant === "danger" ? colors.negative : colors.border,
        borderRadius: 8,
        backgroundColor:
          variant === "primary" ? colors.accent : colors.surfaceStrong,
        opacity: disabled ? 0.45 : pressed ? 0.7 : 1,
        justifyContent: "center",
        alignItems: "center",
      })}
    >
      {loading ? (
        <ActivityIndicator color={colors.positive} />
      ) : (
        <Text
          style={{
            fontFamily: "monospace",
            fontSize: 15,
            fontWeight: "700",
            color:
              variant === "primary"
                ? colors.accentText
                : variant === "danger"
                  ? colors.negative
                  : colors.text,
            textAlign: "center",
          }}
        >
          {children}
        </Text>
      )}
    </Pressable>
  );
}
export function Field({
  label,
  error,
  ...props
}: TextInputProps & { label: string; error?: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ gap: 6 }}>
      <Body size={14}>{label}</Body>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={colors.muted}
        style={{
          minHeight: 50,
          borderWidth: 1,
          borderColor: error ? colors.negative : colors.border,
          borderRadius: 8,
          padding: 12,
          color: colors.text,
          backgroundColor: colors.surfaceStrong,
          fontFamily: "monospace",
          fontSize: 16,
        }}
        {...props}
      />
      {error ? <Body>{error}</Body> : null}
    </View>
  );
}
export function Notice({ children }: PropsWithChildren) {
  const { colors } = useTheme();
  return (
    <View
      accessibilityLiveRegion="polite"
      style={{
        padding: 14,
        borderRadius: 8,
        borderWidth: 1,
        borderLeftWidth: 3,
        borderColor: colors.border,
        borderLeftColor: colors.positive,
        backgroundColor: colors.surface,
      }}
    >
      <Body muted size={14}>
        {children}
      </Body>
    </View>
  );
}
export function Disclosure({
  label,
  children,
  defaultOpen = false,
}: PropsWithChildren<{ label: string; defaultOpen?: boolean }>) {
  const [open, setOpen] = useState(defaultOpen);
  const { colors } = useTheme();
  return (
    <View style={{ gap: open ? 12 : 0 }}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((current) => !current)}
        style={({ pressed }) => ({
          minHeight: 48,
          paddingVertical: 10,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          opacity: pressed ? 0.7 : 1,
        })}
      >
        <Text style={{ flex: 1, color: colors.muted, fontFamily: "monospace", fontSize: 14 }}>
          {label}
        </Text>
        <Text accessible={false} style={{ color: colors.positive, fontFamily: "monospace", fontSize: 18 }}>
          {open ? "−" : "+"}
        </Text>
      </Pressable>
      {open ? <View style={{ gap: 12 }}>{children}</View> : null}
    </View>
  );
}
export function Screen({ children }: PropsWithChildren) {
  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{
          padding: 20,
          paddingBottom: 48,
          gap: 16,
          flexGrow: 1,
        }}
      >
        {children}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
export function Row({ label, value }: { label: string; value: ReactNode }) {
  const { colors } = useTheme();
  return (
    <View
      style={{
        flexDirection: "row",
        flexWrap: "wrap",
        justifyContent: "space-between",
        alignItems: "baseline",
        gap: 8,
        paddingVertical: 8,
        borderBottomWidth: 1,
        borderColor: colors.border,
      }}
    >
      <Body muted size={14}>
        {label}
      </Body>
      <Body size={14}>{value}</Body>
    </View>
  );
}
export function Choice<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (next: T) => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={{ gap: 8 }}>
      <Body size={14}>{label}</Body>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {options.map((option) => (
          <Pressable
            key={option.value}
            accessibilityRole="radio"
            accessibilityLabel={option.label}
            accessibilityState={{ checked: value === option.value }}
            onPress={() => onChange(option.value)}
            style={{
              minHeight: 48,
              borderWidth: 1,
              borderColor:
                value === option.value ? colors.positive : colors.border,
              borderRadius: 8,
              padding: 12,
              justifyContent: "center",
              backgroundColor:
                value === option.value ? colors.surfaceStrong : colors.surface,
            }}
          >
            <Body size={14}>{option.label}</Body>
          </Pressable>
        ))}
      </View>
    </View>
  );
}
