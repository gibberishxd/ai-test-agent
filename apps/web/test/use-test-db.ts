// Runs before each test file's imports: point lib/db at the test database, never the dev one.
// The code under test connects as ata_web (WEB_DATABASE_URL); DATABASE_URL is the admin one.
if (process.env.TEST_DATABASE_URL) {
  process.env.WEB_DATABASE_URL = process.env.TEST_DATABASE_URL;
  process.env.DATABASE_URL = process.env.TEST_ADMIN_DATABASE_URL ?? process.env.TEST_DATABASE_URL;
}

export const hasTestDb = Boolean(process.env.TEST_DATABASE_URL);
