from setuptools import setup, find_packages

setup(
    name="productify-node",
    version="1.2.0",
    description="Productify Node — Physical GPU & Compute Provider Desktop Client & Daemon",
    author="Productify",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pystray>=0.19.5",
        "pillow>=10.0.0",
        "pywebview>=5.0.0",
        "customtkinter>=5.2.0",
    ],
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
