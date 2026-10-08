# SignPath Setup (Required for Signed Installers)

SignPath is used for free code signing (SignPath Foundation certificate). The application must be submitted on signpath.org.

## Steps to complete
1. Go to https://about.signpath.io and create an account (or sign in).
2. Submit the SignPath application for the Slingshot Tools project (tbougnar/Slingshot-Tools).
3. Once approved, create a project and signing policy for Windows .exe installers.
4. Configure GitHub Actions integration using the SignPath GitHub Connector.
5. Add required secrets to the repo (e.g., SIGNPATH_API_TOKEN, SIGNPATH_ORGANIZATION_ID, SIGNPATH_PROJECT_SLUG, SIGNPATH_SIGNING_POLICY_SLUG).
6. Add a signing step in the installer job (monday-verify.yml) to submit the built installer to SignPath and download the signed artifact before upload/publish.

## Current state
- Installers are built unsigned via NSIS (makensis) in the Windows installer job.
- Policy/documents reference SignPath, but CI integration is not configured.
- Until signed, Windows SmartScreen may show warnings.
