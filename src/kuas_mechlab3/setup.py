import os
from glob import glob

from setuptools import find_packages, setup

package_name = "kuas_mechlab3"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (
            os.path.join("share", package_name, "launch"),
            glob(os.path.join("launch", "*launch.py")),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Koyu Fuke",
    maintainer_email="k.fuke@emobi.co.jp",
    description="KUAS MechLab3 ROS2 package.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "mbed_driver = kuas_mechlab3.drive.mbed_driver:main",
            "teleop_keyboard = kuas_mechlab3.drive.teleop_keyboard:main",
            "teleop_server = kuas_mechlab3.drive.teleop_server:main",
            "teleop_ws_client = kuas_mechlab3.drive.teleop_ws_client:main",
            "camera_node = kuas_mechlab3.camera.camera_node:main",
            "mjpeg_server = kuas_mechlab3.camera.mjpeg_server:main",
            "record_server = kuas_mechlab3.record_server:main",
            "traffic_light = kuas_mechlab3.traffic.traffic_light_node:main",
            "traffic_subscriber = kuas_mechlab3.traffic.traffic_subscriber:main",
            "led_indicator = kuas_mechlab3.traffic.led_indicator:main",
        ],
    },
)
