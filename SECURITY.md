# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Binsai, please report it by emailing [pj.patriciojulian@gmail.com](mailto:pj.patriciojulian@gmail.com).

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to provide a timeline for resolution within 7 days.

## Security Best Practices

When using Binsai in production:

1. **API Keys**: Store API keys in environment variables, never in code
2. **Prompt Injection**: Use `δ_artifact_integrity` drive to detect and resist prompt injection
3. **State Validation**: Validate all agent state transitions
4. **Audit Logs**: Enable comprehensive logging for agent decisions
5. **Rate Limiting**: Implement rate limiting for LLM calls

## Safe AI Features

Binsai includes built-in features for safer AI deployment:

- `δ_artifact_integrity`: Monitors for model tampering and injection attacks
- `δ_safety`: Tracks safety-critical state deviations
- `TriProcessArbitrator`: Provides circuit breakers and intervention policies
- Symbolic validation: Validates LLM reasoning through formal methods
