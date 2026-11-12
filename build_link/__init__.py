"""DubTrackr build link: lets the DubTrackr app's "Build it for me" drive Minecraft through
AutoClickr's input, with every safety stop owned here (see engine.py)."""

from .engine import BuildEngine, Stopped, StepError, validate_actions, STOP_REASONS
from .server import BuildLinkServer, link_file_path


def start(version, busy):
    """Starts the real engine and its server; returns (server or None, error text or None)."""
    try:
        from .winput import WindowsBackend
        engine = BuildEngine(WindowsBackend(), busy=busy)
        server = BuildLinkServer(engine, version=version)
        server.start()
        return server, None
    except Exception as exc:  # the rest of AutoClickr keeps working without it
        return None, str(exc)
