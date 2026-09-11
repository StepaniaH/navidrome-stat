const fs = require("fs/promises");
const os = require("os");
const path = require("path");

module.exports = async function globalTeardown(config) {
  const databasePath = config.webServer?.env?.DATABASE_URL;
  if (typeof databasePath !== "string") return;

  const resolvedPath = path.resolve(databasePath);
  const tempDirectory = path.resolve(os.tmpdir());
  const filename = path.basename(resolvedPath);
  if (
    path.dirname(resolvedPath) !== tempDirectory
    || !/^navidrome-stat-e2e-\d+\.sqlite$/.test(filename)
  ) {
    throw new Error(`Refusing to remove unexpected E2E database: ${resolvedPath}`);
  }

  await Promise.all(
    ["", "-wal", "-shm"].map((suffix) =>
      fs.rm(`${resolvedPath}${suffix}`, { force: true }),
    ),
  );
};
