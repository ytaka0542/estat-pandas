from setuptools import setup, find_packages

setup(
    name="estat_pandas",
    version="0.1.2",
    packages=find_packages(exclude=["examples*", "tests*"]),
    install_requires=[
        "pandas<2.2.0",
        "requests",
        "pandas_datareader",
    ],
    author="ytaka0542",
    description="A pandas-datareader extension for e-Stat API",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/ytaka0542/estat-pandas",
)
