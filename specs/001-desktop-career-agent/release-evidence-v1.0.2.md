# CareerOS Local v1.0.2 release evidence

Date: 2026-07-19

Tag: [`v1.0.2`](https://github.com/ejupi-djenis30/careeros-local/releases/tag/v1.0.2)

Commit: `865a7e16a8c52605f20a5586e25539f3a754e7f3`

The public release is neither a draft nor a prerelease and is marked as the latest release.
The community packages are unsigned; platform trust dialogs may therefore appear.

## Verification runs

| Gate | Result | Evidence |
|---|---|---|
| Python, React, Rust and container CI | Passed | [CI run 29670027485](https://github.com/ejupi-djenis30/careeros-local/actions/runs/29670027485) |
| Six-platform release rehearsal | Passed | [Rehearsal 29670029972](https://github.com/ejupi-djenis30/careeros-local/actions/runs/29670029972) |
| Immutable tag build and publication | Passed | [Release run 29670568470](https://github.com/ejupi-djenis30/careeros-local/actions/runs/29670568470) |

Both release runs passed supply-chain audits, sidecar architecture verification, packaged
backend lifecycle checks, native package extraction and reopen checks. Windows x64 and ARM64
also passed MSI extraction plus real silent NSIS install/uninstall smoke tests. The assembly
gate rejected filename collisions and required exactly 17 release files before publication.

## Native package inventory

| Platform | Artifact | Bytes | GitHub asset SHA-256 |
|---|---|---:|---|
| Windows x64 | `CareerOS.Local_1.0.2_x64-setup.exe` | 32,873,244 | `3810b8dcdc5d5df248644a467822f246df01a817ac472b28158613b89cd0d807` |
| Windows x64 | `CareerOS.Local_1.0.2_x64_en-US.msi` | 41,804,925 | `f3b66eea583f3271d6b01fb3e27b5836e55de4eb32d8134c69bd85094f8db2b4` |
| Windows ARM64 | `CareerOS.Local_1.0.2_arm64-setup.exe` | 29,135,739 | `d2958174407e4dbeb2b17f20d41f1f59ce5b47cda0438b268995d6899ae8b607` |
| Windows ARM64 | `CareerOS.Local_1.0.2_arm64_en-US.msi` | 36,265,627 | `a5d763806af7194587c96a81d39901409d2a7c1ec6b8fa4b96451a7899ea2fe5` |
| macOS Intel | `CareerOS.Local_1.0.2_x64.dmg` | 51,924,564 | `4d20bd1149127fdd3a16f1a244f11fdc320da9cfda6dbe98e2544ddd423fb50a` |
| macOS Apple Silicon | `CareerOS.Local_1.0.2_aarch64.dmg` | 49,268,576 | `03b7db30565e0f136dd54b32e8dbb7ca4cca245151912ff36b96d9ffd95a985b` |
| Linux x64 | `CareerOS.Local_1.0.2_amd64.AppImage` | 135,137,784 | `32ada330e74e48b81a980e479ca82c29faa184f2ba3c88c35f062faa61b6339c` |
| Linux x64 | `CareerOS.Local_1.0.2_amd64.deb` | 64,954,226 | `8c6fe0a51c08636633ae852feae22df54de38731591327a8be46bafa2304cfd6` |
| Linux ARM64 | `CareerOS.Local_1.0.2_aarch64.AppImage` | 130,779,656 | `85568c22d2f74797f452f5ecc53289501c3c8eaf847ba72457ed65e46a7d9ac1` |
| Linux ARM64 | `CareerOS.Local_1.0.2_arm64.deb` | 62,202,988 | `9a70ca3a79bfc41e044d83c0ee3c29839d15ec7939aab44fed7568c59809ac4b` |

The remaining seven assets are six target-specific SHA-256 inventories and
`supply-chain-evidence.tar.gz`. Their presence and the complete 17-file count are enforced by
the release workflow before the least-privilege publisher can create a GitHub release.

## Provenance verification

The published Windows ARM64 NSIS package was downloaded again from the public release and
verified against the pinned release workflow identity:

```powershell
gh attestation verify .\CareerOS.Local_1.0.2_arm64-setup.exe `
  --repo ejupi-djenis30/careeros-local `
  --signer-workflow ejupi-djenis30/careeros-local/.github/workflows/desktop-release.yml
```

Result: exit code `0`. The other native packages were attested by the same per-target workflow
step and can be verified with the equivalent command.
