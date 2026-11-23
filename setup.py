from setuptools import setup, find_packages

setup(
    name="estat_pandas",
    version="0.2.0",
    packages=find_packages(exclude=["examples*", "tests*"]),
    package_data={"estat_pandas": ["catalog.json"]},
    python_requires=">=3.8",
    install_requires=[
        "pandas<2.2.0",
        "requests",
        "pandas_datareader",
    ],
    author="ytaka0542",
    description="Catalog-backed access to Japanese economic time series from e-Stat, BOJ, and official CSV sources",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/ytaka0542/estat-pandas",
)
