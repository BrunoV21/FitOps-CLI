import Constants from "expo-constants";

// Set by app.config.js while building; production build scripts force this off.
export const isQaBuild = Constants.expoConfig?.extra?.qaMode === true;
