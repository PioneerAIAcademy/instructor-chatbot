import os


def app_version() -> str | None:
    """The deployed git commit, for Langfuse and Sentry (CLAUDE.md §9.1).

    APP_VERSION is set at image build; on Render, which doesn't pass it, the
    commit comes from RENDER_GIT_COMMIT (shortened like `git rev-parse --short`).
    """
    version = os.getenv("APP_VERSION") or os.getenv("RENDER_GIT_COMMIT", "")[:7]
    return version or None
