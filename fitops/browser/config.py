from __future__ import annotations

import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path

from fitops.config.settings import FitOpsSettings, get_settings
from fitops.utils.exceptions import BrowserPublicationError


@dataclass(frozen=True)
class BrowserProfile:
    browser_type: str
    executable: Path
    user_data_dir: Path
    profile: str

    @property
    def is_open(self) -> bool:
        return any(
            os.path.lexists(self.user_data_dir / marker)
            for marker in ("SingletonLock", "SingletonSocket", "SingletonCookie")
        )

    @property
    def is_default_user_data_dir(self) -> bool:
        """Whether this is the browser's normal OS-level data directory."""
        _, default_data_dir = _browser_defaults(self.browser_type)
        return self.user_data_dir.resolve() == default_data_dir.expanduser().resolve()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["executable"] = str(self.executable)
        data["user_data_dir"] = str(self.user_data_dir)
        data["is_open"] = self.is_open
        data["is_default_user_data_dir"] = self.is_default_user_data_dir
        return data


def _browser_defaults(browser_type: str) -> tuple[Path, Path]:
    system = platform.system()
    home = Path.home()
    values: dict[str, dict[str, tuple[str, str]]] = {
        "Darwin": {
            "brave": (
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "Library/Application Support/BraveSoftware/Brave-Browser",
            ),
            "chrome": (
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "Library/Application Support/Google/Chrome",
            ),
            "edge": (
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "Library/Application Support/Microsoft Edge",
            ),
        },
        "Linux": {
            "brave": ("/usr/bin/brave-browser", ".config/BraveSoftware/Brave-Browser"),
            "chrome": ("/usr/bin/google-chrome", ".config/google-chrome"),
            "edge": ("/usr/bin/microsoft-edge", ".config/microsoft-edge"),
        },
        "Windows": {
            "brave": (
                "BraveSoftware/Brave-Browser/Application/brave.exe",
                "BraveSoftware/Brave-Browser/User Data",
            ),
            "chrome": (
                "Google/Chrome/Application/chrome.exe",
                "Google/Chrome/User Data",
            ),
            "edge": (
                "Microsoft/Edge/Application/msedge.exe",
                "Microsoft/Edge/User Data",
            ),
        },
    }
    executable, data_dir = values.get(system, values["Linux"])[browser_type]
    if system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home))
        return local / executable, local / data_dir
    return Path(executable), home / data_dir


def resolve_browser_profile(
    settings: FitOpsSettings | None = None,
) -> BrowserProfile:
    settings = settings or get_settings()
    requested = (settings.browser_type or "").lower()
    candidates = [requested] if requested else ["brave", "chrome", "edge"]
    candidates = [item for item in candidates if item in {"brave", "chrome", "edge"}]
    if not candidates:
        raise BrowserPublicationError(
            "Browser type must be brave, chrome, or edge.", code="browser_invalid"
        )

    for browser_type in candidates:
        default_executable, default_data = _browser_defaults(browser_type)
        executable = Path(
            settings.browser_executable or default_executable
        ).expanduser()
        user_data = Path(settings.browser_user_data_dir or default_data).expanduser()
        if executable.is_file() and user_data.is_dir():
            return BrowserProfile(
                browser_type=browser_type,
                executable=executable,
                user_data_dir=user_data,
                profile=settings.browser_profile or "Default",
            )

    raise BrowserPublicationError(
        "No supported browser profile was found. Configure one with "
        "`fitops browser configure` or FITOPS_BROWSER_* environment variables.",
        code="browser_not_configured",
        status_code=409,
    )


def ensure_profile_available(profile: BrowserProfile) -> None:
    if profile.is_open:
        raise BrowserPublicationError(
            f"The {profile.browser_type} profile '{profile.profile}' is already open. "
            "Close every window using that browser profile and retry; FitOps will not copy cookies.",
            code="browser_profile_in_use",
            status_code=409,
        )
