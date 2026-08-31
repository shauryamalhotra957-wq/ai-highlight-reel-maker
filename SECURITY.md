# Security policy

Uploaded video, audio, transcripts, captions, and rendered clips may contain private or copyrighted material.

- Do not commit source media, rendered clips, transcripts, provider credentials, or generated job directories.
- Keep API keys server-side and do not expose them through the static client.
- Treat uploaded filenames and media as untrusted input; use the bounded upload path and avoid shell interpolation when invoking FFmpeg.
- Review generated clips and captions for sensitive content before sharing result URLs.
- Demo mode should be used for deterministic tests and examples.

Report suspected path traversal, command injection, credential exposure, or accidental media disclosure privately to the repository owner with sanitized reproduction steps. Do not disclose active vulnerabilities publicly.
