module.exports = ({ config }) => {
  const qaMode = process.env.FITOPS_QA_BUILD === "1";
  return {
    ...config,
    name: qaMode ? "FitOps QA" : "FitOps",
    extra: { ...config.extra, qaMode },
  };
};
