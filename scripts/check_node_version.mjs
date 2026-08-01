import { pathToFileURL } from "node:url";

const SUPPORTED_NODE_RANGE = ">=24.18.0 <25";

export function parseNodeVersion(value) {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(String(value));
  if (!match) return null;
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
  };
}

export function isSupportedNodeVersion(value) {
  const parsed = parseNodeVersion(value);
  if (!parsed || parsed.major !== 24) return false;
  return parsed.minor > 18 || (parsed.minor === 18 && parsed.patch >= 0);
}

export function requireSupportedNodeVersion(value = process.versions.node) {
  if (!isSupportedNodeVersion(value)) {
    throw new Error(
      `CareerOS requires Node.js ${SUPPORTED_NODE_RANGE}; received ${String(value)}.`,
    );
  }
  return value;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const version = requireSupportedNodeVersion();
    process.stdout.write(`CAREEROS_NODE_RUNTIME_OK version=${version}\n`);
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}
