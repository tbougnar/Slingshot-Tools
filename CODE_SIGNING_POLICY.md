# Code signing policy

Free code signing provided by SignPath.io, certificate by SignPath Foundation.

## Team roles and members

| Role | Member |
|---|---|
| Maintainer, developer, release manager | Taha Bougnar — owner of `tbougnar/Slingshot-Tools` |

The same team is responsible for development, maintenance, source ownership and
for producing every signed artifact. There are no upstream or third-party
source files in the signed artifacts.

## What we sign

- Windows installer `.exe` files for our desktop utilities, published on the
  product's download page and on GitHub Releases.

## How the artifacts are produced

Artifacts are built from the source in this public repository, in GitHub
Actions, using the build scripts that live in the same repository. Only
artifacts produced by that pipeline are submitted for signing. The private key
is never held in this repository or on any machine we control.

## Scope and limitations

- Only artifacts built from this repository's source code are signed.
- SignPath Foundation publishes the artifact for verification.
- Signing is limited to our own projects and our own binaries.

## Verification

Users can verify a download by checking the file properties in Windows and
confirming that the signature is valid and that the publisher is
**SignPath Foundation**.