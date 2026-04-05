from setuptools import find_packages, setup

setup(
    name="mac-butler",
    version="4.0",
    packages=find_packages(exclude=["venv*", "*.egg-info"]),
    py_modules=["butler", "butler_config", "state", "trigger"],
)
