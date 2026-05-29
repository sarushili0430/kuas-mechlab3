from setuptools import find_packages, setup

package_name = "kuas_mechlab3"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Koyu Fuke",
    maintainer_email="k.fuke@emobi.co.jp",
    description="KUAS MechLab3 ROS2 package.",
    license="Apache-2.0",
    entry_points={"console_scripts": []},
)
