// Runs before each test file's imports: point lib/db at the test database, never the dev one.
if (process.env.TEST_DATABASE_URL) process.env.DATABASE_URL = process.env.TEST_DATABASE_URL;

export const hasTestDb = Boolean(process.env.TEST_DATABASE_URL);
