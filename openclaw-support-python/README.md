# OpenClaw Support Python

Supporting Python scripts used around local OpenClaw operations.

## Folders

- `shared/` - reusable OpenClaw utilities such as dry runs, load tests, and QR HTML conversion.
- `davina/` - Davina Helo Wedding support scripts.
- `yasmin/` - Yasmin Zahira Wedding support scripts.
- `moura/` - Moura Alexandra support scripts and tests.
- `evals/` - local evaluation runners copied from OpenClaw workspaces.
- `minipc/` - MiniPC operational alert and cleanup helpers.

## Notes

These scripts expect local OpenClaw paths, credentials, and services to be configured on the target machine. Secrets are referenced through environment variables or local credential files and should not be committed.
