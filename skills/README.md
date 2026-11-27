# skills/

Company skills for the Meels Paperclip agents, versioned in git.
Only skills written for Meels live here; built-in Paperclip skills do not.

- One directory per skill: `skills/<name>/`.
- Each directory has a `SKILL.md` with frontmatter containing `name` (same as the directory) and `description`.
- Changes go through a pull request only, like the rest of this repo.

This directory is not deployed: the GitOps controller does not map `skills/` to any LXC or host path.

Skills:

- `buffering-onderzoek`: fixed procedure for Plex/Jellyfin buffering complaints.
