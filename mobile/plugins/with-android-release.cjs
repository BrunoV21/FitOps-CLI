const { withAppBuildGradle, withGradleProperties } = require("expo/config-plugins");

// Keep generated native output reproducible. Production builds never fall back to a debug key.
module.exports = function withAndroidRelease(config) {
  config = withGradleProperties(config, (result) => {
    const values = {
      "org.gradle.jvmargs": "-Xmx4096m -XX:MaxMetaspaceSize=1536m",
      "org.gradle.workers.max": "4",
    };
    for (const [key, value] of Object.entries(values)) {
      const property = result.modResults.find((item) => item.type === "property" && item.key === key);
      if (property) property.value = value;
      else result.modResults.push({ type: "property", key, value });
    }
    return result;
  });
  return withAppBuildGradle(config, (result) => {
    let source = result.modResults.contents;
    if (source.includes("// FitOps release signing")) return result;
    source = source.replace(
      "signingConfigs {",
      `signingConfigs {
        // FitOps release signing: all owner-managed values must be supplied together.
        release {
            def signingPath = System.getenv('FITOPS_KEYSTORE_PATH')
            if (signingPath) {
                storeFile file(signingPath)
                storePassword System.getenv('FITOPS_KEYSTORE_PASSWORD')
                keyAlias System.getenv('FITOPS_KEY_ALIAS')
                keyPassword System.getenv('FITOPS_KEY_PASSWORD')
            }
        }`,
    );
    const release =
      /release\s*\{\s*\/\/ Caution![\s\S]*?signingConfig signingConfigs\.debug/;
    if (!release.test(source))
      throw new Error(
        "FitOps signing plugin could not locate the generated release build type. Review the Android template before building.",
      );
    source = source.replace(release, (match) =>
      match.replace(
        "signingConfig signingConfigs.debug",
        "if (System.getenv('FITOPS_KEYSTORE_PATH')) { signingConfig signingConfigs.release }",
      ),
    );
    // Insert an explicitly named internal variant after the release block, without modifying debug.
    const marker = "buildTypes {";
    source = source.replace(
      marker,
      `${marker}
        internal {
            initWith release
            applicationIdSuffix '.internal'
            versionNameSuffix '-internal'
            signingConfig signingConfigs.debug
            matchingFallbacks = ['release']
        }`,
    );
    result.modResults.contents = source;
    return result;
  });
};
