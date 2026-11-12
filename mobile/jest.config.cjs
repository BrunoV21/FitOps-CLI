module.exports = { preset: 'jest-expo', testMatch: ['**/src/**/*.test.[jt]s?(x)'], moduleNameMapper: { '^@/(.*)$': '<rootDir>/src/$1' }, setupFilesAfterEnv: ['<rootDir>/src/test/setup.ts'] };
