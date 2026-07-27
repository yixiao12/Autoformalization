# Code Agent Safety Policy

Each numbered statement is an atomic requirement. A generated Cedar policy
must preserve the requirement ID in its `@source` annotation.

1. **CAG-001 — Sensitive writes.** The agent must not use `Write` on paths containing `.env`, `credentials`, or `secrets`.
2. **CAG-002 — Sensitive edits.** The agent must not use `Edit` on `.env`, `id_rsa`, or `.pem` files.
3. **CAG-003 — Git metadata integrity.** The agent must not use `Write` or `Edit` on files under a `.git` directory.
4. **CAG-004 — Sensitive reads.** The agent must not use `Read` on `.env` files, SSH private keys, PEM files, or AWS credential files.
5. **CAG-005 — Secret-oriented search.** The agent must not use `Grep` to search for private-key headers, `API_KEY=`, or `password=` assignments.
6. **CAG-006 — Sensitive directory discovery.** The agent must not use `Glob` to enumerate `.ssh`, `.aws`, or `.git` directory contents.
7. **CAG-007 — Private-key creation.** The agent must not write content containing a private-key header.
8. **CAG-008 — Secret insertion.** The agent must not edit a file by inserting a private-key header, `AWS_SECRET_ACCESS_KEY`, or `API_KEY=` assignment.
9. **CAG-009 — Destructive deletion.** The agent must not execute commands that recursively force-delete the filesystem root or the current user's home directory.
10. **CAG-010 — Disk destruction.** The agent must not execute filesystem-formatting commands or overwrite a disk with data from `/dev/zero`.
11. **CAG-011 — Raw-device redirection.** The agent must not redirect command output into `/dev/sd*` block devices.
12. **CAG-012 — Host shutdown.** The agent must not execute `shutdown`, `reboot`, `poweroff`, or `halt` commands.
13. **CAG-013 — Privilege escalation.** The agent must not execute commands through `sudo` or switch to a root shell with `su -`.
14. **CAG-014 — Remote script execution.** The agent must not pipe content downloaded by `curl` or `wget` directly into a shell.
15. **CAG-015 — Command timeout.** A `Bash` timeout must not exceed 300000 milliseconds.
16. **CAG-016 — Secure web transport.** `WebFetch` may only fetch HTTPS URLs.
17. **CAG-017 — Untrusted fetch sources.** `WebFetch` must not fetch from Pastebin, raw GitHub content, or GitHub Gists.
18. **CAG-018 — Credential-hunting searches.** `WebSearch` must not search for password dumps, leaked credentials, or exposed API keys.
19. **CAG-019 — Private-key output.** Tool output containing a private-key header must be denied.
20. **CAG-020 — Cloud-secret output.** Tool output containing `AWS_SECRET_ACCESS_KEY` or `SECRET_TOKEN=` must be denied.

