# Security Policy

## Security Model

FlexBE Synthesis is intended for use in trusted development, lab, and robot networks. It does not enforce network isolation, authentication, authorization, sandboxing, or other security controls, and it should not be treated as a security boundary.

Do not expose synthesis action servers, generated artifacts, launch files, or Slugs-related command execution paths to untrusted users or networks without adding external security controls appropriate for your deployment.

## Supported Versions

Version 0.0.1 is the current supported release, available on the `main` branch. Security fixes target `main`.

## Reporting a Vulnerability

Please do not open a public issue for vulnerabilities involving unsafe command execution, path traversal, arbitrary file writes, generated-code execution, or malformed input that can affect a robot or operator environment.

Report security concerns privately to:

```text
robotics@cnu.edu
```

Include:

- Affected package and version or commit.
- Steps to reproduce.
- Any relevant YAML/spec/action request inputs.
- Expected impact and whether the issue is actively exploitable.

The maintainers will acknowledge receipt and coordinate a fix before public disclosure when appropriate.
