"""MCP server exposing the KUAS MechLab3 robot's teleop / camera / recording
channels as tools for a local Claude (stdio transport, no authentication).

Intended to run on a machine on the robot's LAN, alongside the MCP client
(e.g. Claude Code). It speaks the robot's existing wire protocols as a client
and does not require ROS 2."""

__all__ = ["config", "teleop", "camera", "record"]
__version__ = "0.1.0"
