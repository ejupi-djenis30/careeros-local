import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(fileURLToPath(new URL("../", import.meta.url)));

test("keeps frame embedding protection in response headers instead of ineffective meta CSP", async () => {
    const [indexHtml, nginxConfig, nginxMainConfig, nginxApiProxy] = await Promise.all([
        readFile(resolve(repositoryRoot, "frontend/index.html"), "utf8"),
        readFile(resolve(repositoryRoot, "frontend/nginx.conf"), "utf8"),
        readFile(resolve(repositoryRoot, "frontend/nginx-main.conf"), "utf8"),
        readFile(resolve(repositoryRoot, "frontend/nginx-api-proxy.conf"), "utf8"),
    ]);
    const metaCsp = indexHtml.match(
        /<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"/i,
    )?.[1];

    assert(metaCsp, "Frontend document must retain its local-runtime meta CSP");
    assert(
        !metaCsp.includes("frame-ancestors"),
        "frame-ancestors is ignored in meta CSP and must not generate a browser warning",
    );
    assert.match(
        nginxConfig,
        /Content-Security-Policy\s+"[^"]*frame-ancestors 'none'[^"]*"/,
        "Web distribution must send frame-ancestors as an HTTP response header",
    );
    assert.match(nginxConfig, /X-Frame-Options\s+"DENY"/);
    const permissionPolicies = [
        ...`${nginxApiProxy}\n${nginxConfig}`.matchAll(/Permissions-Policy\s+"([^"]+)"/g),
    ].map((match) => match[1]);
    assert.deepEqual(permissionPolicies, [
        "camera=(), microphone=(), geolocation=(), display-capture=(), payment=(), usb=()",
        "camera=(), microphone=(), geolocation=(), display-capture=(), payment=(), usb=()",
        "camera=(), microphone=(), geolocation=(self), display-capture=(), payment=(), usb=()",
    ]);
    assert.match(
        nginxMainConfig,
        /log_format privacy '\$status \$request_method \$request_time'/,
    );
    assert.doesNotMatch(
        nginxMainConfig,
        /\$(?:uri|request_uri|remote_addr|args)\b/,
        "Distribution access logs must not persist private targets or client addresses",
    );
    assert.match(nginxMainConfig, /error_log \/dev\/stderr crit;/);
    assert.match(nginxMainConfig, /\bgzip on;/);
    assert.match(nginxMainConfig, /\bgzip_vary on;/);
    assert.match(nginxMainConfig, /\bgzip_min_length 1024;/);
    assert.match(nginxApiProxy, /\bgzip off;/);
    assert.match(
        nginxApiProxy,
        /proxy_hide_header Cache-Control;[\s\S]*?proxy_hide_header Pragma;/,
    );
    assert.match(
        nginxConfig,
        /location = \/api\/v1\/portability\/(?:inspect|restore) \{\s*client_max_body_size 129m;/,
    );
    assert.match(nginxConfig, /location \/api\/ \{\s*client_max_body_size 11m;/);
    assert.match(
        nginxConfig,
        /error_page 413 = @request_body_too_large;[\s\S]*?location @request_body_too_large \{[\s\S]*?default_type application\/json;[\s\S]*?return 413 '\{"detail":"File too large or request body exceeds the local processing limit\."\}';/,
    );
    assert.equal(
        [...nginxConfig.matchAll(/include \/etc\/nginx\/conf\.d\/careeros-api-proxy\.inc;/g)].length,
        3,
    );
    assert.match(
        nginxConfig,
        /location \/ \{[\s\S]*?Cache-Control "no-cache, must-revalidate"/,
    );
    assert.match(
        nginxConfig,
        /location ~\* "\^\/assets\/\.\+-\[a-z0-9_-\]\{8,\}[^"]+"\s+\{/,
        "The comma-bearing fingerprint regex must be quoted for valid Nginx syntax",
    );
    assert.doesNotMatch(
        nginxConfig,
        /\bexpires\s+1y;/,
        "Fingerprint caching must emit one unambiguous Cache-Control field",
    );
    assert.match(
        nginxConfig,
        /location \/assets\/ \{[\s\S]*?Cache-Control "no-cache, must-revalidate"/,
    );
    assert.doesNotMatch(
        nginxConfig,
        /location ~\* \\\.\(\?:css\|js\|woff2\?\|svg\)/,
        "Unhashed root assets must not be cached as immutable",
    );
    assert.doesNotMatch(nginxConfig, /error_page\s+500\s+502\s+503\s+504/);
});

test("loads only lifecycle CSS and icons before the authenticated workspace", async () => {
    const [entrypoint, workspace, workspaceCss] = await Promise.all([
        readFile(resolve(repositoryRoot, "frontend/src/main.jsx"), "utf8"),
        readFile(resolve(repositoryRoot, "frontend/src/app/AuthenticatedWorkspace.jsx"), "utf8"),
        readFile(resolve(repositoryRoot, "frontend/src/app/workspace-bootstrap.css"), "utf8"),
    ]);

    assert.match(entrypoint, /shell-icons\.css/);
    assert.match(entrypoint, /shell\.css/);
    assert.doesNotMatch(entrypoint, /bootstrap-icons-subset\.css/);
    assert.doesNotMatch(entrypoint, /(?:index|career-os)\.css/);
    assert.doesNotMatch(entrypoint, /bootstrap-icons\/font\/bootstrap-icons\.css/);
    assert.doesNotMatch(entrypoint, /bootstrap\/dist\/css\/bootstrap\.min\.css/);
    assert.match(workspace, /bootstrap-icons-subset\.css/);
    assert.match(workspace, /index\.css/);
    assert.match(workspace, /career-os\.css/);
    assert.match(workspace, /workspace-bootstrap\.css/);
    const workspaceStyleOrder = [
        "bootstrap-icons-subset.css",
        "index.css",
        "career-os.css",
        "workspace-bootstrap.css",
    ].map((stylesheet) => workspace.indexOf(stylesheet));
    assert(workspaceStyleOrder.every((position) => position >= 0));
    assert.deepEqual(
        workspaceStyleOrder,
        [...workspaceStyleOrder].sort((left, right) => left - right),
        "Authenticated CSS imports must preserve the established icon, legacy, design-system and Bootstrap cascade",
    );
    assert.match(
        workspaceCss,
        /bootstrap\/dist\/css\/bootstrap\.min\.css" layer\(careeros-bootstrap\)/,
        "Legacy Bootstrap CSS must load only with the authenticated workspace",
    );
});

test("binds the distributable third-party notices to every dependency lock", async () => {
    const [notice, generator, viteConfig] = await Promise.all([
        readFile(resolve(repositoryRoot, "THIRD_PARTY_NOTICES.txt"), "utf8"),
        readFile(resolve(repositoryRoot, "scripts/third_party_notices.py"), "utf8"),
        readFile(resolve(repositoryRoot, "frontend/vite.config.js"), "utf8"),
    ]);
    const approved = generator.match(/APPROVED_NOTICE_SHA256 = "([0-9a-f]{64})"/)?.[1];
    const actual = createHash("sha256").update(notice).digest("hex");
    assert.equal(actual, approved, "Canonical third-party notices must match the approved digest");

    const manifestText = notice
        .split("----- BEGIN CAREEROS THIRD-PARTY MANIFEST -----\n", 2)[1]
        ?.split("\n----- END CAREEROS THIRD-PARTY MANIFEST -----", 1)[0];
    assert(manifestText, "Third-party notices must contain their machine-checkable manifest");
    const manifest = JSON.parse(manifestText);
    assert.deepEqual(manifest.componentCounts, {
        frontend: 12,
        python: 55,
        runtime: 3,
        rust: 484,
    });
    for (const [relativePath, expectedHash] of Object.entries(manifest.sourceLocks)) {
        const payload = await readFile(resolve(repositoryRoot, relativePath));
        assert.equal(
            createHash("sha256").update(payload).digest("hex"),
            expectedHash,
            `${relativePath} changed without regenerated third-party notices`,
        );
    }
    assert.match(viteConfig, /fileName:\s*'THIRD_PARTY_NOTICES\.txt'/);
});
