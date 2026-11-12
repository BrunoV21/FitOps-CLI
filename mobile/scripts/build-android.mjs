import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const variant = process.argv[2] ?? "internal";
if (!["internal", "release"].includes(variant))
  throw new Error("Choose internal or release.");
const signing = [
  "FITOPS_KEYSTORE_PATH",
  "FITOPS_KEYSTORE_PASSWORD",
  "FITOPS_KEY_ALIAS",
  "FITOPS_KEY_PASSWORD",
];
if (process.env.FITOPS_KEYSTORE_PATH)
  process.env.FITOPS_KEYSTORE_PATH = resolve(process.env.FITOPS_KEYSTORE_PATH);
const buildEnvironment = {
  ...process.env,
  NODE_ENV: process.env.NODE_ENV ?? "production",
  FITOPS_QA_BUILD: variant === "internal" ? "1" : "0",
};
const present = signing.filter((name) => process.env[name]);
if (
  variant === "release" &&
  present.length &&
  present.length !== signing.length
)
  throw new Error(
    "Production signing requires all four FITOPS_KEYSTORE_* / FITOPS_KEY_* variables.",
  );
if (
  variant === "release" &&
  process.env.FITOPS_KEYSTORE_PATH &&
  !existsSync(process.env.FITOPS_KEYSTORE_PATH)
)
  throw new Error("The configured signing keystore file does not exist.");
function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    stdio: "inherit",
    env: buildEnvironment,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
run(
  "npx",
  ["expo", "prebuild", "--platform", "android", "--no-install"],
  process.cwd(),
);
run(
  "./gradlew",
  [
    variant === "internal" ? "assembleInternal" : "assembleRelease",
    "-Dorg.gradle.internal.http.socketTimeout=180000",
    "-Dorg.gradle.internal.http.connectionTimeout=30000",
    ...(variant === "internal"
      ? [
          `-PreactNativeArchitectures=${process.env.FITOPS_ANDROID_ARCHITECTURES ?? "arm64-v8a"}`,
        ]
      : []),
  ],
  `${process.cwd()}/android`,
);
console.log(
  variant === "internal"
    ? "Internal APK: android/app/build/outputs/apk/internal/app-internal.apk (test signing; not for AppGallery)"
    : present.length
      ? "Signed release APK: android/app/build/outputs/apk/release/app-release.apk"
      : "Unsigned release APK: android/app/build/outputs/apk/release/app-release-unsigned.apk (owner signing required)",
);
