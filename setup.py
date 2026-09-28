from setuptools import setup, find_packages

setup(
    name="productify-node",
    version="1.0.0",
    description="Productify Node — Physical GPU & Compute Provider Desktop Client",
    author="Productify",
    packages=find_packages(),
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "productify-node = main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
