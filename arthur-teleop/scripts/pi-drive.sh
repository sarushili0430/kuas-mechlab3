#!/bin/bash
# Pi-side teleop launcher for the ML3 4-motor robot drivetrain.
#
# Sources ROS 2 Humble + the team workspace, sets ROS_DOMAIN_ID=11 (Team 11's
# domain — keeps our nodes isolated from other teams on ml3_5G), and runs
# the keyboard teleop node (w/a/s/d/q + 1-4 jog -> four motor setpoints over /dev/ttyACM0).
#
# Deploy:
#   scp scripts/pi-drive.sh ml3@<pi-ip>:~/drive.sh
#   ssh ml3@<pi-ip> 'chmod +x ~/drive.sh'
#
# Run on the Pi:
#   bash ~/drive.sh
# or remotely-launched into the Pi's HDMI display:
#   ssh ml3@<pi-ip> 'DISPLAY=:0 mate-terminal --title="ML3 Motor Teleop" -e "bash ~/drive.sh" &'

set -e

export ROS_DOMAIN_ID=11

if [ -f /opt/ros/humble/setup.bash ]; then
    # shellcheck disable=SC1091
    source /opt/ros/humble/setup.bash
else
    echo "error: ROS 2 Humble not found at /opt/ros/humble" >&2
    exit 1
fi

WS="${HOME}/ros2_ws"
if [ -f "${WS}/install/setup.bash" ]; then
    # shellcheck disable=SC1091
    source "${WS}/install/setup.bash"
else
    echo "error: workspace not built — run 'cd ${WS} && colcon build' first" >&2
    exit 1
fi

clear
cat <<'BANNER'
============================================
      ML3 4-Motor Teleop (mbed_motor_ctrl)
============================================
   HOLD a key to move — release to stop:
   w = forward        s = backward
   a = turn left      d = turn right
   q = emergency stop      1/2/3/4 = hold to jog one wheel (FL/BL/BR/FR)
   Ctrl+C = exit (auto-stops)
============================================
BANNER

# Disable -e for the ROS run itself — we want to fall through to the
# "press enter to close" prompt even if the node exits non-zero.
set +e
ros2 run mbedros2 mbed_motor_ctrl
EXIT=$?
set -e

echo
echo "--- Node exited (status ${EXIT}). Press Enter to close this terminal. ---"
read -r
