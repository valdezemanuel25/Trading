"""Push the bot's state to a git branch (default "tjl-state") so the next job, a restarted job and Claude's daily
report all read the same files. The state checkout lives in its own directory (a clone of that branch)."""
import subprocess
import time

from . import settings as S


class GitSync:
    def __init__(self, path, branch="tjl-state", every=S.GIT_SYNC_SECONDS):
        self.path, self.branch, self.every = path, branch, every
        self.last = 0.0

    def _git(self, *args, check=True):
        return subprocess.run(["git", "-C", self.path, *args], check=check, capture_output=True, text=True)

    def __call__(self, force=False):
        if not force and time.monotonic() - self.last < self.every:
            return
        self.last = time.monotonic()
        self._git("add", "-A")
        if self._git("diff", "--cached", "--quiet", check=False).returncode != 0:
            self._git("commit", "-q", "-m", f"tjl-bot state {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._git("pull", "-q", "--rebase", "origin", self.branch, check=False)   # picks up HALT / FLATTEN too
        self._git("push", "-q", "origin", f"HEAD:{self.branch}")
